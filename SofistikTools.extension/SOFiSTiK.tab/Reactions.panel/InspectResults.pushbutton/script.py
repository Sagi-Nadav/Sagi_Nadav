# -*- coding: utf-8 -*-
"""Read-only diagnostic: can the SOFiSTiK reaction results be scheduled in Revit?

Answers one question before we build anything: are the reaction numbers you see
in the SOFiSTiK Result View real Revit elements (schedulable, taggable) or just
AVF graphics painted onto the view (not schedulable, ever)?

Reports for the active view and the current selection:
  * whether an Analysis Visualization Framework (AVF) manager owns the results
  * a census of every category present in the view
  * per element: category, API class, and whether Revit allows scheduling it
  * every parameter each result element carries, so we can spot Fx / Fy / Fz

Opens no transaction and changes nothing in the model.
"""

from pyrevit import revit, DB, script

output = script.get_output()
output.set_width(1100)

doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView

# Categories worth inspecting in detail even when nothing is selected.
INTERESTING_HINTS = ('analytic', 'analysis', 'sofistik', 'result', 'node')


def safe_name(element):
    """Element.Name is ambiguous under IronPython, so guard it."""
    try:
        return element.Name
    except Exception:
        return ''


def param_value(param):
    """Best-effort readable value for a parameter of any storage type."""
    storage = param.StorageType
    if storage == DB.StorageType.String:
        return param.AsString() or ''
    if storage == DB.StorageType.ElementId:
        eid = param.AsElementId()
        if eid is None or eid.IntegerValue < 0:
            return ''
        target = doc.GetElement(eid)
        return safe_name(target) if target else str(eid.IntegerValue)
    # Double and Integer both format nicely through AsValueString.
    return param.AsValueString() or ''


def category_of(element):
    try:
        return element.Category
    except Exception:
        return None


def is_schedulable(category):
    """True when Revit would offer this category in the New Schedule dialog."""
    if category is None:
        return False
    try:
        return DB.ViewSchedule.IsValidCategoryForSchedule(category.Id)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1. Active view + AVF check -- this is the decisive test
# ---------------------------------------------------------------------------
output.print_md('# SOFiSTiK result inspector')
output.print_md('## 1. Active view')
output.print_md('- **Name:** `{}`'.format(active_view.Name))
output.print_md('- **View type:** `{}`'.format(active_view.ViewType))
output.print_md('- **API class:** `{}`'.format(active_view.GetType().FullName))

sfm = None
try:
    sfm = DB.Analysis.SpatialFieldManager.GetSpatialFieldManager(active_view)
except Exception as err:
    output.print_md('- AVF lookup failed: `{}`'.format(err))

if sfm is None:
    output.print_md(
        '- **AVF:** no SpatialFieldManager on this view. '
        'The results are *not* AVF graphics, so they are probably real elements.'
    )
else:
    registered = []
    try:
        registered = list(sfm.GetRegisteredResults())
    except Exception:
        pass
    output.print_md(
        '- **AVF: this view HAS a SpatialFieldManager** '
        '({} registered result(s), {} measurement(s)).'.format(
            len(registered), sfm.NumberOfMeasurements
        )
    )
    output.print_md(
        '  > Values drawn through AVF are pure graphics. They carry no '
        'parameters and **cannot be put in a Revit schedule**.'
    )

# ---------------------------------------------------------------------------
# 2. Category census of the active view
# ---------------------------------------------------------------------------
output.print_md('## 2. What actually lives in this view')

view_elements = DB.FilteredElementCollector(doc, active_view.Id) \
                  .WhereElementIsNotElementType() \
                  .ToElements()

census = {}
for el in view_elements:
    cat = category_of(el)
    key = cat.Name if cat is not None else '<no category>'
    entry = census.setdefault(key, {'count': 0, 'cat': cat, 'sample': el})
    entry['count'] += 1

rows = []
for name in sorted(census, key=lambda n: -census[n]['count']):
    entry = census[name]
    rows.append([
        name,
        entry['count'],
        'YES' if is_schedulable(entry['cat']) else 'no',
        entry['sample'].GetType().Name,
    ])

if rows:
    output.print_table(
        table_data=rows,
        columns=['Category', 'Count', 'Schedulable?', 'API class'],
    )
else:
    output.print_md('_No model elements found in this view._')

# ---------------------------------------------------------------------------
# 3. Detailed parameter dump
# ---------------------------------------------------------------------------
output.print_md('## 3. Parameters on the result elements')

targets = [doc.GetElement(eid) for eid in uidoc.Selection.GetElementIds()]

if targets:
    output.print_md('_Inspecting your current selection ({} element(s))._'.format(len(targets)))
else:
    # Nothing selected: auto-pick one sample per interesting category.
    for name in sorted(census):
        if any(hint in name.lower() for hint in INTERESTING_HINTS):
            targets.append(census[name]['sample'])
    output.print_md(
        '_Nothing selected, so showing one sample per analysis-related category. '
        'Select a reaction value in the view and re-run for a precise answer._'
    )

if not targets:
    output.print_md('**No candidate elements found.** Select a reaction label and re-run.')

for el in targets:
    if el is None:
        continue
    cat = category_of(el)
    cat_name = cat.Name if cat is not None else '<no category>'

    output.print_md('### {} - id {}'.format(cat_name, el.Id.IntegerValue))
    output.print_md('- **API class:** `{}`'.format(el.GetType().FullName))
    output.print_md('- **Schedulable category:** {}'.format(
        'YES' if is_schedulable(cat) else 'NO'
    ))
    output.print_md('- **Select / zoom:** {}'.format(output.linkify(el.Id)))

    param_rows = []
    for param in el.Parameters:
        definition = param.Definition
        if definition is None:
            continue
        param_rows.append([
            definition.Name,
            str(param.StorageType).replace('StorageType.', ''),
            param_value(param),
            'shared' if param.IsShared else 'built-in',
            'read-only' if param.IsReadOnly else 'writable',
        ])

    if param_rows:
        param_rows.sort(key=lambda r: r[0])
        output.print_table(
            table_data=param_rows,
            columns=['Parameter', 'Type', 'Value', 'Origin', 'Access'],
        )
    else:
        output.print_md('_This element exposes no parameters at all._')

# ---------------------------------------------------------------------------
# 4. Verdict
# ---------------------------------------------------------------------------
output.print_md('## 4. Read this part')
output.print_md(
    'A Revit schedule needs two things: a **schedulable category** and '
    '**parameters holding the values**. Check section 3 above:'
)
output.print_md(
    '- If the result elements say `Schedulable category: YES` and you can see '
    'Fx / Fy / Fz style parameters in the table, we can build a schedule '
    'directly on them.\n'
    '- If they say `NO`, or the parameter table is empty, or section 1 reported '
    'an AVF SpatialFieldManager, then the numbers are display-only. In that case '
    'we push the reactions onto the structural elements (or onto a small support '
    'family placed at each node) as shared parameters, and schedule those instead.'
)
