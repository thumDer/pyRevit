from pyrevit import revit, script, forms, DB

logger = script.get_logger()
doc = revit.doc

cfg = script.get_config()
logger.debug('loaded config {}'.format(cfg))
line_category = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
line_subcategories = line_category.SubCategories
line_styles = [
    lsc.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
    for lsc in line_subcategories
]
line_styles.sort(key=lambda x: x.Name)

line_style = forms.SelectFromList.show(
    line_styles,
    name_attr='Name',
    title='Select Line Style to be used'
)
if line_style:
    cfg.line_style = line_style.Name
    script.save_config()
    logger.debug('saved selected line style to config')
