using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using Autodesk.Revit.UI;
using Newtonsoft.Json.Linq;

namespace RevitMcp
{
    /// <summary>
    /// All commands the MCP server can call. Every command runs on Revit's main thread.
    /// Lengths in and out are in meters; areas in m², volumes in m³.
    /// Requires Revit 2024 or newer (64-bit ElementId).
    /// </summary>
    public static class Commands
    {
        public static JToken Dispatch(UIApplication app, string name, JObject a)
        {
            switch (name)
            {
                case "get_model_info": return GetModelInfo(app);
                case "list_levels": return ListLevels(Doc(app));
                case "list_views": return ListViews(Doc(app));
                case "set_active_view": return SetActiveView(app, a);
                case "list_elements": return ListElements(Doc(app), a);
                case "list_types": return ListTypes(Doc(app), a);
                case "get_element": return GetElement(Doc(app), a);
                case "get_selection": return GetSelection(app);
                case "select_elements": return SelectElements(app, a);
                case "set_parameter": return SetParameter(Doc(app), a);
                case "create_level": return CreateLevel(Doc(app), a);
                case "create_wall": return CreateWall(Doc(app), a);
                case "create_floor": return CreateFloor(Doc(app), a);
                case "place_column": return PlaceColumn(Doc(app), a);
                case "create_beam": return CreateBeam(Doc(app), a);
                case "move_elements": return MoveElements(Doc(app), a);
                case "delete_elements": return DeleteElements(Doc(app), a);
                case "get_quantities": return GetQuantities(Doc(app), a);
                default: throw new ArgumentException("Unknown command: " + name);
            }
        }

        // ------------------------------------------------------------------ helpers

        private static Document Doc(UIApplication app)
        {
            var doc = app.ActiveUIDocument?.Document;
            if (doc == null) throw new InvalidOperationException("No model is open in Revit.");
            return doc;
        }

        private static double ToFt(double meters) => UnitUtils.ConvertToInternalUnits(meters, UnitTypeId.Meters);
        private static double M(double feet) => Math.Round(UnitUtils.ConvertFromInternalUnits(feet, UnitTypeId.Meters), 4);
        private static double M2(double sqft) => Math.Round(UnitUtils.ConvertFromInternalUnits(sqft, UnitTypeId.SquareMeters), 4);
        private static double M3(double cuft) => Math.Round(UnitUtils.ConvertFromInternalUnits(cuft, UnitTypeId.CubicMeters), 4);

        private static long IdOf(ElementId id) => id.Value;
        private static ElementId ToId(JToken t) => new ElementId((long)t);

        private static List<ElementId> Ids(JObject a, string key = "ids")
        {
            var arr = a[key] as JArray ?? throw new ArgumentException($"'{key}' must be an array of element ids.");
            return arr.Select(ToId).ToList();
        }

        private static XYZ Pt(JToken t, double z = 0)
        {
            var arr = t as JArray ?? throw new ArgumentException("A point must be [x, y] or [x, y, z] in meters.");
            double x = (double)arr[0], y = (double)arr[1];
            double zz = arr.Count > 2 ? (double)arr[2] : z;
            return new XYZ(ToFt(x), ToFt(y), ToFt(zz));
        }

        private static readonly Dictionary<string, BuiltInCategory> CategoryAliases =
            new Dictionary<string, BuiltInCategory>(StringComparer.OrdinalIgnoreCase)
            {
                ["walls"] = BuiltInCategory.OST_Walls,
                ["floors"] = BuiltInCategory.OST_Floors,
                ["slabs"] = BuiltInCategory.OST_Floors,
                ["columns"] = BuiltInCategory.OST_StructuralColumns,
                ["structural columns"] = BuiltInCategory.OST_StructuralColumns,
                ["architectural columns"] = BuiltInCategory.OST_Columns,
                ["beams"] = BuiltInCategory.OST_StructuralFraming,
                ["framing"] = BuiltInCategory.OST_StructuralFraming,
                ["foundations"] = BuiltInCategory.OST_StructuralFoundation,
                ["rebar"] = BuiltInCategory.OST_Rebar,
                ["doors"] = BuiltInCategory.OST_Doors,
                ["windows"] = BuiltInCategory.OST_Windows,
                ["rooms"] = BuiltInCategory.OST_Rooms,
                ["levels"] = BuiltInCategory.OST_Levels,
                ["grids"] = BuiltInCategory.OST_Grids,
                ["roofs"] = BuiltInCategory.OST_Roofs,
                ["stairs"] = BuiltInCategory.OST_Stairs,
                ["furniture"] = BuiltInCategory.OST_Furniture,
                ["generic models"] = BuiltInCategory.OST_GenericModel,
            };

        private static BuiltInCategory Category(string s)
        {
            if (string.IsNullOrWhiteSpace(s)) throw new ArgumentException("'category' is required.");
            if (CategoryAliases.TryGetValue(s.Trim(), out var bic)) return bic;
            string n = s.Trim().Replace(" ", "");
            if (!n.StartsWith("OST_", StringComparison.OrdinalIgnoreCase)) n = "OST_" + n;
            if (Enum.TryParse(n, true, out bic)) return bic;
            throw new ArgumentException($"Unknown category '{s}'. Use e.g. walls, floors, columns, beams, foundations, or a BuiltInCategory like OST_Walls.");
        }

        private static Level FindLevel(Document doc, JToken t, bool required = true)
        {
            var levels = new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                .OrderBy(l => l.Elevation).ToList();
            if (levels.Count == 0) throw new InvalidOperationException("The model has no levels.");
            if (t == null || t.Type == JTokenType.Null)
            {
                if (required) return levels[0];
                return null;
            }
            if (t.Type == JTokenType.Integer)
            {
                var byId = doc.GetElement(ToId(t)) as Level;
                if (byId != null) return byId;
            }
            string name = t.ToString();
            return levels.FirstOrDefault(l => string.Equals(l.Name, name, StringComparison.OrdinalIgnoreCase))
                   ?? levels.FirstOrDefault(l => l.Name.IndexOf(name, StringComparison.OrdinalIgnoreCase) >= 0)
                   ?? throw new ArgumentException($"Level '{name}' not found. Available: {string.Join(", ", levels.Select(l => l.Name))}");
        }

        /// <summary>Finds an element type by "Type", "Family: Type" or id. Returns null if name is empty.</summary>
        private static T FindType<T>(Document doc, JToken t, BuiltInCategory? bic = null) where T : ElementType
        {
            if (t == null || t.Type == JTokenType.Null || t.ToString() == "") return null;
            if (t.Type == JTokenType.Integer && doc.GetElement(ToId(t)) is T byId) return byId;

            var col = new FilteredElementCollector(doc).OfClass(typeof(T));
            if (bic.HasValue) col = col.OfCategory(bic.Value);
            var types = col.Cast<T>().ToList();
            string name = t.ToString();
            T match = types.FirstOrDefault(x => string.Equals($"{x.FamilyName}: {x.Name}", name, StringComparison.OrdinalIgnoreCase))
                      ?? types.FirstOrDefault(x => string.Equals(x.Name, name, StringComparison.OrdinalIgnoreCase))
                      ?? types.FirstOrDefault(x => x.Name.IndexOf(name, StringComparison.OrdinalIgnoreCase) >= 0);
            if (match == null)
                throw new ArgumentException($"Type '{name}' not found. Available: " +
                    string.Join(", ", types.Take(40).Select(x => $"{x.FamilyName}: {x.Name}")));
            return match;
        }

        private static JObject Run(Document doc, string title, Func<JObject> action)
        {
            using (var tx = new Transaction(doc, "MCP: " + title))
            {
                tx.Start();
                var opts = tx.GetFailureHandlingOptions();
                opts.SetFailuresPreprocessor(new WarningSwallower());
                opts.SetClearAfterRollback(true);
                tx.SetFailureHandlingOptions(opts);
                JObject result;
                try { result = action(); }
                catch { tx.RollBack(); throw; }
                var status = tx.Commit();
                if (status != TransactionStatus.Committed)
                    throw new InvalidOperationException("Revit rejected the change (" + status + ").");
                return result;
            }
        }

        /// <summary>Removes warnings so no dialog blocks Revit; real errors still fail the transaction.</summary>
        private class WarningSwallower : IFailuresPreprocessor
        {
            public FailureProcessingResult PreprocessFailures(FailuresAccessor fa)
            {
                foreach (var f in fa.GetFailureMessages())
                    if (f.GetSeverity() == FailureSeverity.Warning) fa.DeleteWarning(f);
                return FailureProcessingResult.Continue;
            }
        }

        private static JObject Summary(Document doc, Element e)
        {
            var o = new JObject
            {
                ["id"] = IdOf(e.Id),
                ["name"] = e.Name,
                ["category"] = e.Category?.Name,
            };
            var typeId = e.GetTypeId();
            if (typeId != ElementId.InvalidElementId && doc.GetElement(typeId) is ElementType et)
                o["type"] = $"{et.FamilyName}: {et.Name}";
            if (e.LevelId != ElementId.InvalidElementId && doc.GetElement(e.LevelId) is Level lv)
                o["level"] = lv.Name;
            return o;
        }

        private static JToken ParamValue(Parameter p)
        {
            switch (p.StorageType)
            {
                case StorageType.String: return p.AsString();
                case StorageType.Integer: return p.AsValueString() ?? p.AsInteger().ToString();
                case StorageType.Double: return p.AsValueString();
                case StorageType.ElementId:
                    var id = p.AsElementId();
                    var el = p.Element?.Document.GetElement(id);
                    return el != null ? $"{el.Name} (id {IdOf(id)})" : IdOf(id).ToString();
                default: return null;
            }
        }

        // ------------------------------------------------------------------ read

        private static JToken GetModelInfo(UIApplication app)
        {
            var doc = Doc(app);
            return new JObject
            {
                ["title"] = doc.Title,
                ["path"] = doc.PathName,
                ["revit_version"] = app.Application.VersionNumber,
                ["is_family"] = doc.IsFamilyDocument,
                ["active_view"] = doc.ActiveView?.Name,
                ["levels"] = ListLevels(doc),
                ["counts"] = new JObject
                {
                    ["walls"] = Count(doc, BuiltInCategory.OST_Walls),
                    ["floors"] = Count(doc, BuiltInCategory.OST_Floors),
                    ["structural_columns"] = Count(doc, BuiltInCategory.OST_StructuralColumns),
                    ["beams"] = Count(doc, BuiltInCategory.OST_StructuralFraming),
                    ["foundations"] = Count(doc, BuiltInCategory.OST_StructuralFoundation),
                    ["doors"] = Count(doc, BuiltInCategory.OST_Doors),
                    ["windows"] = Count(doc, BuiltInCategory.OST_Windows),
                }
            };
        }

        private static int Count(Document doc, BuiltInCategory bic) =>
            new FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().GetElementCount();

        private static JArray ListLevels(Document doc) =>
            new JArray(new FilteredElementCollector(doc).OfClass(typeof(Level)).Cast<Level>()
                .OrderBy(l => l.Elevation)
                .Select(l => new JObject { ["id"] = IdOf(l.Id), ["name"] = l.Name, ["elevation_m"] = M(l.Elevation) }));

        private static JArray ListViews(Document doc) =>
            new JArray(new FilteredElementCollector(doc).OfClass(typeof(View)).Cast<View>()
                .Where(v => !v.IsTemplate && v.CanBePrinted)
                .OrderBy(v => v.ViewType.ToString()).ThenBy(v => v.Name)
                .Select(v => new JObject { ["id"] = IdOf(v.Id), ["name"] = v.Name, ["view_type"] = v.ViewType.ToString() }));

        private static JToken SetActiveView(UIApplication app, JObject a)
        {
            var doc = Doc(app);
            View view = null;
            if (a["id"] != null) view = doc.GetElement(ToId(a["id"])) as View;
            if (view == null && a["name"] != null)
            {
                string n = (string)a["name"];
                view = new FilteredElementCollector(doc).OfClass(typeof(View)).Cast<View>()
                    .FirstOrDefault(v => !v.IsTemplate && string.Equals(v.Name, n, StringComparison.OrdinalIgnoreCase));
            }
            if (view == null) throw new ArgumentException("View not found.");
            app.ActiveUIDocument.ActiveView = view;
            return new JObject { ["active_view"] = view.Name };
        }

        private static JToken ListElements(Document doc, JObject a)
        {
            var bic = Category((string)a["category"]);
            int limit = (int?)a["limit"] ?? 200;
            var level = FindLevel(doc, a["level"], required: false);
            var all = new FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
                .Where(e => level == null || e.LevelId == level.Id).ToList();
            return new JObject
            {
                ["total"] = all.Count,
                ["returned"] = Math.Min(limit, all.Count),
                ["elements"] = new JArray(all.Take(limit).Select(e => Summary(doc, e)))
            };
        }

        private static JToken ListTypes(Document doc, JObject a)
        {
            var bic = Category((string)a["category"]);
            return new JArray(new FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType()
                .Cast<ElementType>()
                .OrderBy(t => t.FamilyName).ThenBy(t => t.Name)
                .Select(t => new JObject { ["id"] = IdOf(t.Id), ["family"] = t.FamilyName, ["name"] = t.Name }));
        }

        private static JToken GetElement(Document doc, JObject a)
        {
            var e = doc.GetElement(ToId(a["id"])) ?? throw new ArgumentException("Element not found.");
            var o = Summary(doc, e);
            if (e.Location is LocationPoint lp)
                o["location"] = new JArray(M(lp.Point.X), M(lp.Point.Y), M(lp.Point.Z));
            else if (e.Location is LocationCurve lc)
            {
                var c = lc.Curve;
                o["start"] = new JArray(M(c.GetEndPoint(0).X), M(c.GetEndPoint(0).Y), M(c.GetEndPoint(0).Z));
                o["end"] = new JArray(M(c.GetEndPoint(1).X), M(c.GetEndPoint(1).Y), M(c.GetEndPoint(1).Z));
                o["length_m"] = M(c.Length);
            }
            var ps = new JObject();
            foreach (Parameter p in e.Parameters)
            {
                if (p.Definition == null || !p.HasValue) continue;
                string key = p.Definition.Name;
                if (ps.ContainsKey(key)) continue;
                ps[key] = ParamValue(p);
            }
            o["parameters"] = ps;
            if ((bool?)a["include_type_parameters"] == true && doc.GetElement(e.GetTypeId()) is ElementType et)
            {
                var tps = new JObject();
                foreach (Parameter p in et.Parameters)
                    if (p.Definition != null && p.HasValue && !tps.ContainsKey(p.Definition.Name))
                        tps[p.Definition.Name] = ParamValue(p);
                o["type_parameters"] = tps;
            }
            return o;
        }

        private static JToken GetSelection(UIApplication app)
        {
            var doc = Doc(app);
            var ids = app.ActiveUIDocument.Selection.GetElementIds();
            return new JArray(ids.Select(id => doc.GetElement(id)).Where(e => e != null).Select(e => Summary(doc, e)));
        }

        private static JToken SelectElements(UIApplication app, JObject a)
        {
            var ids = Ids(a);
            var uidoc = app.ActiveUIDocument;
            uidoc.Selection.SetElementIds(ids);
            if ((bool?)a["zoom"] ?? true)
            {
                try { if (ids.Count > 0) uidoc.ShowElements(ids); } catch { }
            }
            return new JObject { ["selected"] = ids.Count };
        }

        private static JToken GetQuantities(Document doc, JObject a)
        {
            var bic = Category((string)a["category"]);
            var level = FindLevel(doc, a["level"], required: false);
            var elems = new FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()
                .Where(e => level == null || e.LevelId == level.Id);

            double Get(Element e, BuiltInParameter bip)
            {
                var p = e.get_Parameter(bip);
                return p != null && p.HasValue && p.StorageType == StorageType.Double ? p.AsDouble() : 0;
            }

            var groups = elems.GroupBy(e =>
            {
                var t = doc.GetElement(e.GetTypeId()) as ElementType;
                return t != null ? $"{t.FamilyName}: {t.Name}" : "(no type)";
            });

            var rows = new JArray();
            double tv = 0, ta = 0, tl = 0; int tc = 0;
            foreach (var g in groups.OrderBy(g => g.Key))
            {
                double v = g.Sum(e => Get(e, BuiltInParameter.HOST_VOLUME_COMPUTED));
                double ar = g.Sum(e => Get(e, BuiltInParameter.HOST_AREA_COMPUTED));
                double l = g.Sum(e => Math.Max(Get(e, BuiltInParameter.CURVE_ELEM_LENGTH), Get(e, BuiltInParameter.INSTANCE_LENGTH_PARAM)));
                int c = g.Count();
                tv += v; ta += ar; tl += l; tc += c;
                rows.Add(new JObject { ["type"] = g.Key, ["count"] = c, ["volume_m3"] = M3(v), ["area_m2"] = M2(ar), ["length_m"] = M(l) });
            }
            return new JObject
            {
                ["category"] = bic.ToString(),
                ["level"] = level?.Name,
                ["by_type"] = rows,
                ["total"] = new JObject { ["count"] = tc, ["volume_m3"] = M3(tv), ["area_m2"] = M2(ta), ["length_m"] = M(tl) }
            };
        }

        // ------------------------------------------------------------------ modify

        private static JToken SetParameter(Document doc, JObject a)
        {
            var e = doc.GetElement(ToId(a["id"])) ?? throw new ArgumentException("Element not found.");
            string pname = (string)a["parameter"];
            string value = a["value"]?.ToString() ?? "";
            bool onType = (bool?)a["on_type"] ?? false;
            Element target = onType ? doc.GetElement(e.GetTypeId()) : e;
            if (target == null) throw new ArgumentException("Element has no type.");
            var p = target.LookupParameter(pname)
                    ?? throw new ArgumentException($"Parameter '{pname}' not found on {(onType ? "type" : "element")}.");
            if (p.IsReadOnly) throw new InvalidOperationException($"Parameter '{pname}' is read-only.");

            return Run(doc, "Set " + pname, () =>
            {
                bool ok;
                switch (p.StorageType)
                {
                    case StorageType.String:
                        ok = p.Set(value); break;
                    case StorageType.Integer:
                        if (bool.TryParse(value, out bool b)) ok = p.Set(b ? 1 : 0);
                        else if (value == "כן") ok = p.Set(1);
                        else if (value == "לא") ok = p.Set(0);
                        else ok = p.Set(int.Parse(value, CultureInfo.InvariantCulture));
                        break;
                    case StorageType.Double:
                        // Value in the project's display units, e.g. "3000" (mm) or "3 m".
                        ok = p.SetValueString(value);
                        if (!ok && double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out double d))
                            ok = p.Set(UnitUtils.ConvertToInternalUnits(d, p.GetUnitTypeId()));
                        break;
                    case StorageType.ElementId:
                        ok = p.Set(new ElementId(long.Parse(value, CultureInfo.InvariantCulture))); break;
                    default: ok = false; break;
                }
                if (!ok) throw new InvalidOperationException($"Could not set '{pname}' to '{value}'.");
                return new JObject { ["id"] = IdOf(target.Id), ["parameter"] = pname, ["new_value"] = ParamValue(p) };
            });
        }

        private static JToken CreateLevel(Document doc, JObject a)
        {
            double elev = (double)a["elevation_m"];
            string name = (string)a["name"];
            return Run(doc, "Create level", () =>
            {
                var lv = Level.Create(doc, ToFt(elev));
                if (!string.IsNullOrEmpty(name)) lv.Name = name;
                return new JObject { ["id"] = IdOf(lv.Id), ["name"] = lv.Name, ["elevation_m"] = M(lv.Elevation) };
            });
        }

        private static JToken CreateWall(Document doc, JObject a)
        {
            var level = FindLevel(doc, a["level"]);
            var wt = FindType<WallType>(doc, a["wall_type"]);
            var typeId = wt?.Id ?? doc.GetDefaultElementTypeId(ElementTypeGroup.WallType);
            double height = (double?)a["height_m"] ?? 3.0;
            double offset = (double?)a["base_offset_m"] ?? 0;
            bool structural = (bool?)a["structural"] ?? false;
            var p1 = Pt(a["start"]); var p2 = Pt(a["end"]);
            p1 = new XYZ(p1.X, p1.Y, level.Elevation); p2 = new XYZ(p2.X, p2.Y, level.Elevation);

            return Run(doc, "Create wall", () =>
            {
                var w = Wall.Create(doc, Line.CreateBound(p1, p2), typeId, level.Id, ToFt(height), ToFt(offset), false, structural);
                return Summary(doc, w);
            });
        }

        private static JToken CreateFloor(Document doc, JObject a)
        {
            var level = FindLevel(doc, a["level"]);
            var ft = FindType<FloorType>(doc, a["floor_type"]);
            var typeId = ft?.Id ?? doc.GetDefaultElementTypeId(ElementTypeGroup.FloorType);
            bool structural = (bool?)a["structural"] ?? true;
            var pts = (a["points"] as JArray ?? throw new ArgumentException("'points' must be a list of [x, y]."))
                .Select(t => Pt(t, 0)).Select(p => new XYZ(p.X, p.Y, level.Elevation)).ToList();
            if (pts.Count < 3) throw new ArgumentException("A floor needs at least 3 points.");

            var loop = new CurveLoop();
            for (int i = 0; i < pts.Count; i++)
                loop.Append(Line.CreateBound(pts[i], pts[(i + 1) % pts.Count]));

            return Run(doc, "Create floor", () =>
            {
                var f = Floor.Create(doc, new List<CurveLoop> { loop }, typeId, level.Id, structural, null, 0);
                if (a["offset_m"] != null)
                    f.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM)?.Set(ToFt((double)a["offset_m"]));
                return Summary(doc, f);
            });
        }

        private static FamilySymbol Symbol(Document doc, JToken typeName, BuiltInCategory bic)
        {
            var sym = FindType<FamilySymbol>(doc, typeName, bic)
                      ?? new FilteredElementCollector(doc).OfClass(typeof(FamilySymbol)).OfCategory(bic)
                          .Cast<FamilySymbol>().FirstOrDefault();
            if (sym == null) throw new InvalidOperationException($"No family of category {bic} is loaded in the project. Load one first.");
            return sym;
        }

        private static JToken PlaceColumn(Document doc, JObject a)
        {
            bool structural = (bool?)a["structural"] ?? true;
            var bic = structural ? BuiltInCategory.OST_StructuralColumns : BuiltInCategory.OST_Columns;
            var sym = Symbol(doc, a["column_type"], bic);
            var baseLevel = FindLevel(doc, a["base_level"]);
            var topLevel = FindLevel(doc, a["top_level"], required: false);
            var points = a["points"] as JArray ?? new JArray(a["location"] ?? throw new ArgumentException("Give 'location' [x,y] or 'points' [[x,y],...]."));

            return Run(doc, "Place columns", () =>
            {
                if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
                var created = new JArray();
                foreach (var t in points)
                {
                    var p = Pt(t, 0);
                    var fi = doc.Create.NewFamilyInstance(new XYZ(p.X, p.Y, baseLevel.Elevation), sym, baseLevel,
                        structural ? StructuralType.Column : StructuralType.NonStructural);
                    if (topLevel != null)
                        fi.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)?.Set(topLevel.Id);
                    created.Add(Summary(doc, fi));
                }
                return new JObject { ["created"] = created };
            });
        }

        private static JToken CreateBeam(Document doc, JObject a)
        {
            var sym = Symbol(doc, a["beam_type"], BuiltInCategory.OST_StructuralFraming);
            var level = FindLevel(doc, a["level"]);
            var p1 = Pt(a["start"]); var p2 = Pt(a["end"]);
            p1 = new XYZ(p1.X, p1.Y, level.Elevation); p2 = new XYZ(p2.X, p2.Y, level.Elevation);
            return Run(doc, "Create beam", () =>
            {
                if (!sym.IsActive) { sym.Activate(); doc.Regenerate(); }
                var fi = doc.Create.NewFamilyInstance(Line.CreateBound(p1, p2), sym, level, StructuralType.Beam);
                return Summary(doc, fi);
            });
        }

        private static JToken MoveElements(Document doc, JObject a)
        {
            var ids = Ids(a);
            var v = Pt(a["vector"]);
            return Run(doc, "Move elements", () =>
            {
                ElementTransformUtils.MoveElements(doc, ids, v);
                return new JObject { ["moved"] = ids.Count };
            });
        }

        private static JToken DeleteElements(Document doc, JObject a)
        {
            var ids = Ids(a);
            return Run(doc, "Delete elements", () =>
            {
                var deleted = doc.Delete(ids);
                return new JObject { ["requested"] = ids.Count, ["deleted_including_dependents"] = deleted.Count };
            });
        }
    }
}
