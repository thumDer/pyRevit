# -*- coding: UTF-8 -*-

#pylint: disable=E0401,invalid-name,missing-docstring,broad-except,bare-except
import traceback
from pyrevit import revit, script, forms, EXEC_PARAMS

from Autodesk.Revit import DB
from Autodesk.Revit.Exceptions import (
    CentralModelContentionException,
    InternalException
)

doc = revit.doc
uidoc = revit.uidoc

logger = script.get_logger()
output = script.get_output()

results = script.get_results()

exceptions = []



class SyncLockCallback(DB.ICentralLockedCallback):
    def ShouldWaitForLockAvailability(self):
        return False

def set_active_view(view):
    if not isinstance(view, DB.View):
        raise TypeError('Element [{}] is not a View!'.format(view.Id.IntegerValue))
    name = view.Name
    if view.ViewType != DB.ViewType.Internal and \
            view.ViewType != DB.ViewType.ProjectBrowser:
        uidoc.ActiveView = view
        logger.debug('Active View is: {}'.format(view.Name))
        return name
    else:
        logger.debug('View {} ({}) cannot be activated.'.format(name, view.ViewType))
        return 'INTERNAL / PB: ' + name

def sync_failed_popup(sub_msg=None):
    return forms.alert(
        'Synchronization Failed! Please check the error output '
        'window for additional information.',
        sub_msg=sub_msg
    )

sync_failed = False

sv_settings = DB.FilteredElementCollector(doc).OfClass(DB.StartingViewSettings).ToElements()[0]

try:
    starting_view_uid = doc.GetElement(sv_settings.ViewId).UniqueId
except AttributeError:
    starting_view_uid = None
presync_view_uid = uidoc.ActiveGraphicalView.UniqueId
if starting_view_uid:
    sync_view_uid = starting_view_uid
else:
    sync_view_uid = presync_view_uid

sync_view = doc.GetElement(sync_view_uid)

logger.debug('Sync View UniqueId: {}'.format(sync_view_uid))

uiviews = uidoc.GetOpenUIViews()
uiview_uids = [doc.GetElement(v.ViewId).UniqueId for v in uiviews]

closed_views = []

try:
    logger.debug('Open Views: {}'.format([view_uid for view_uid in uiview_uids]))

    uidoc.ActiveView = doc.GetElement(sync_view_uid)

    logger.debug('Closing Views:')
    for uiview in uiviews:
        view_uid = doc.GetElement(uiview.ViewId).UniqueId
        # if sync_view is a sheet we need to check if the view to be closed
        # is actually an activated viewport on that sheet
        if isinstance(sync_view, DB.ViewSheet):
            view_to_check = doc.GetElement(view_uid)
            sheet_number = view_to_check.get_Parameter(
                DB.BuiltInParameter.VIEWER_SHEET_NUMBER).AsString()
            if sheet_number == sync_view.SheetNumber:
                continue
        if view_uid != sync_view_uid:
            uiview.Close()
            view_name = doc.GetElement(view_uid).Name
            logger.debug('{} is closed.'.format(view_name))
            closed_views.append(view_name)

    twc_opts = DB.TransactWithCentralOptions()
    trans_callback = SyncLockCallback()
    twc_opts.SetLockCallback(trans_callback)
    swc_opts = DB.SynchronizeWithCentralOptions()
    swc_opts.SetRelinquishOptions(DB.RelinquishOptions(True))
    swc_opts.Comment = 'pyRevit Sync!'
    toast_msg = 'pyRevit Sync finished in {}'.format(doc.Title)
    if EXEC_PARAMS.config_mode:
        swc_opts.Compact = True
        toast_msg += ' with Compact mode Enabled.'

    doc.SynchronizeWithCentral(twc_opts, swc_opts)
    forms.toast(toast_msg)
except CentralModelContentionException:
    sync_failed = True
    logger.warn(
        'The Central Model is locked, because someone else is '
        'synchronizing or opening the model right now, '
        'please try again later. All your views should be restored. '
        'Please check the Worksharing Monitor for additional info!'
    )
    exceptions.append(('Locked model handled.', traceback.format_exc()))
except InternalException as ie:
    sync_failed = True
    logger.warn(
        'Synchronization Failed :(\n'
        'Internal Revit Error, sorry about that. '
        'If it happens again try the original sync button '
        'or try to restart Revit.'
    )
    exceptions.append(('Internal Exception', str(ie), traceback.format_exc()))
except Exception as e:
    sync_failed = True
    try:
        exc_type = type(e).__name__
    except Exception as e:
        exc_type = 'Unknown'
    logger.warn(
        'Synchronization Failed :(\n{}\n{}'.format(exc_type, e),
        exc_info=1
    )
    exceptions.append((exc_type, str(e), traceback.format_exc()))

opened_views = []
logger.debug('Opening Views:')
for view_uid in uiview_uids:
    view_to_open = doc.GetElement(view_uid)
    if isinstance(view_to_open, DB.View):
        try:
            opened_views.append(set_active_view(view_to_open))
        except Exception as e:
            logger.warn(
                'Failed to open following view:\n{}'\
                .format(view_to_open.Name),
                exc_info=1
            )
            exceptions.append((view_to_open.Name, traceback.format_exc()))

try:
    presync_view = doc.GetElement(presync_view_uid)
    if presync_view:
        set_active_view(presync_view)
except Exception as e:
    logger.warn('Failed to restore the original view.', exc_info=1)
    exceptions.append((presync_view_uid.IntegerValue, traceback.format_exc()))

if starting_view_uid not in uiview_uids:
    uiviews = uidoc.GetOpenUIViews()
    for uiview in uiviews:
        if doc.GetElement(uiview.ViewId).UniqueId == starting_view_uid:
            try:
                uiview.Close()
            except:
                logger.warn(
                    'Failed to close View',
                    exc_info=1
                )
                exceptions.append(
                    ('Failed to close view', traceback.format_exc())
                )
            break

try:
    results.presync_view = doc.GetElement(presync_view_uid).Name
except:
    pass
results.closed_views = closed_views
results.opened_views = opened_views
results.exceptions = exceptions

if sync_failed:
    sync_failed_popup()
logger.debug(('Opened views:', opened_views))
