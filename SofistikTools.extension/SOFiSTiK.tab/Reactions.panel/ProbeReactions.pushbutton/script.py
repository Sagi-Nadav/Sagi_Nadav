# -*- coding: utf-8 -*-
"""Read-only probe: where can we get the reaction values, and where do we put them?

InspectResults established that the reactions are AVF graphics and therefore
cannot be scheduled. Two things decide how we build the real tool:

  1. Can the values be read back out of the SpatialFieldManager? If yes we skip
     the SOFiSTiK -> Excel -> Revit round trip entirely. The AVF API is largely
     write-only, so this reflects over the live object rather than assuming.
  2. What parameters do the Analytical Nodes carry? They are the schedulable
     carrier for the values, and we need a join key - ideally a SOFiSTiK node
     number already sitting on the node.

Opens no transaction and changes nothing in the model.
"""

from pyrevit import revit, DB, script

output = script.get_output()
output.set_width(1100)

doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView

MAX_SAMPLES = 3


def safe_name(element):
    try:
        return element.Name
    except Exception:
        return ''


def param_value(param):
    storage = param.StorageType
    if storage == DB.StorageType.String:
        return param.AsString() or ''
    if storage == DB.StorageType.ElementId:
        eid = param.AsElementId()
        if eid is None or eid.IntegerValue < 0:
            return ''
        target = doc.GetElement(eid)
        return safe_name(target) if target else str(eid.IntegerValue)
    return param.AsValueString() or ''


def describe(value, limit=160):
    try:
        text = str(value)
    except Exception as err:
        return '<unprintable: {}>'.format(err)
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit] + ' ...'


output.print_md('# SOFiSTiK reaction probe')

# ---------------------------------------------------------------------------
# 1. What does the AVF result actually contain?
# ---------------------------------------------------------------------------
output.print_md('## 1. The AVF result')

sfm = None
try:
    sfm = DB.Analysis.SpatialFieldManager.GetSpatialFieldManager(active_view)
except Exception as err:
    output.print_md('AVF lookup failed: `{}`'.format(err))

if sfm is None:
    output.print_md(
        '**No SpatialFieldManager on `{}`.** Open the view that actually shows '
        'the reactions and re-run.'.format(active_view.Name)
    )
else:
    output.print_md('- **Measurements:** {}'.format(sfm.NumberOfMeasurements))

    schema_rows = []
    try:
        for idx in sfm.GetRegisteredResults():
            try:
                schema = sfm.GetResultSchema(idx)
                schema_rows.append([
                    idx,
                    getattr(schema, 'Name', ''),
                    getattr(schema, 'Description', ''),
                    describe(getattr(schema, 'Units', '') or
                             getattr(schema, 'Unit', ''), 60),
                ])
            except Exception as err:
                schema_rows.append([idx, '<error>', describe(err, 80), ''])
    except Exception as err:
        output.print_md('Could not enumerate results: `{}`'.format(err))

    if schema_rows:
        output.print_table(
            table_data=schema_rows,
            columns=['Index', 'Schema name', 'Description', 'Units'],
        )

    # The decisive question: is there any public way to read the stored values?
    output.print_md('### Readable API surface on SpatialFieldManager')
    members = [m for m in dir(sfm) if not m.startswith('_')]
    getters = sorted(m for m in members
                     if m.startswith('Get') or m.startswith('Is')
                     or m.startswith('Number') or m.startswith('Contains'))
    output.print_md('`{}`'.format('`, `'.join(getters) if getters else 'none'))
    output.print_md(
        '> If nothing here returns stored field values, AVF is write-only in '
        'this Revit version and the numbers must come from SOFiSTiK directly.'
    )

# ---------------------------------------------------------------------------
# 2. The analytical elements - our schedulable carrier
# ---------------------------------------------------------------------------
output.print_md('## 2. Analytical elements and their parameters')

view_elements = DB.FilteredElementCollector(doc, active_view.Id) \
                  .WhereElementIsNotElementType() \
                  .ToElements()

by_category = {}
for el in view_elements:
    try:
        cat = el.Category
    except Exception:
        continue
    if cat is None or 'analytic' not in cat.Name.lower():
        continue
    by_category.setdefault(cat.Name, []).append(el)

selection = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]
if selection:
    output.print_md('_Using your selection ({} element(s))._'.format(len(selection)))
    samples = [(safe_name(el) or 'selected', [el]) for el in selection]
else:
    output.print_md(
        '_Nothing selected, so showing up to {} sample(s) per analytical '
        'category._'.format(MAX_SAMPLES)
    )
    samples = [(name, by_category[name][:MAX_SAMPLES])
               for name in sorted(by_category)]

if not samples:
    output.print_md('**No analytical elements found in this view.**')

for cat_name, elements in samples:
    for el in elements:
        if el is None:
            continue
        output.print_md('### {} - id {}'.format(cat_name, el.Id.IntegerValue))
        output.print_md('- **API class:** `{}`'.format(el.GetType().FullName))
        output.print_md('- **Select / zoom:** {}'.format(output.linkify(el.Id)))

        rows = []
        for param in el.Parameters:
            definition = param.Definition
            if definition is None:
                continue
            rows.append([
                definition.Name,
                str(param.StorageType).replace('StorageType.', ''),
                param_value(param),
                'shared' if param.IsShared else 'built-in',
                'read-only' if param.IsReadOnly else 'writable',
            ])

        if rows:
            rows.sort(key=lambda r: r[0])
            output.print_table(
                table_data=rows,
                columns=['Parameter', 'Type', 'Value', 'Origin', 'Access'],
            )
        else:
            output.print_md('_No parameters._')

# ---------------------------------------------------------------------------
# 3. Is a SOFiSTiK identifier already present anywhere?
# ---------------------------------------------------------------------------
output.print_md('## 3. Existing SOFiSTiK parameters in the project')

sofistik_params = set()
for elements in by_category.values():
    for el in elements[:50]:
        for param in el.Parameters:
            definition = param.Definition
            if definition is None:
                continue
            lowered = definition.Name.lower()
            if 'sofistik' in lowered or lowered.startswith('sof') \
                    or 'node' in lowered or 'analytical id' in lowered:
                sofistik_params.add(definition.Name)

if sofistik_params:
    output.print_md(
        'Candidate join keys found on analytical elements:\n\n- `{}`'.format(
            '`\n- `'.join(sorted(sofistik_params))
        )
    )
    output.print_md(
        '> If one of these already holds the SOFiSTiK node number, we can match '
        'exported reactions to Revit nodes by number instead of by coordinate.'
    )
else:
    output.print_md(
        'None found. We will have to match SOFiSTiK results to Revit nodes by '
        'XYZ coordinate, then stamp our own ID onto each node.'
    )
