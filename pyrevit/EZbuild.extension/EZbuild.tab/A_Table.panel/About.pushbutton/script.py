# -*- coding: utf-8 -*-
"""
About -- the version, and links to the privacy and code signing policies.

The Autodesk marketplace requires the privacy policy to be reachable from inside
the app, not only from the store listing. This edition is not sold through the
store, but its users are owed the same link, and the two editions keep the same
ribbon. It shows the same dialog as the native add-in's CmdAbout; keep the two
in step. It changes nothing in the document.
"""

from __future__ import unicode_literals

__title__ = 'About'
__doc__ = 'Version, privacy policy, code signing policy and website.'

from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommandLinkId,
                               TaskDialogCommonButtons, TaskDialogResult)
from System.Diagnostics import Process, ProcessStartInfo

from eztable import __version__

PRIVACY_URL = 'https://www.ezbuild.co.nz/for-revit-privacy.html'
CODE_SIGNING_URL = 'https://www.ezbuild.co.nz/code-signing.html'
HOME_URL = 'https://www.ezbuild.co.nz/for-revit.html'


def open_url(url):
    try:
        info = ProcessStartInfo(url)
        # On Revit 2025+ (.NET 8 and later) a bare URL is not an executable
        info.UseShellExecute = True
        Process.Start(info)
    except Exception:
        # No default browser, or a policy blocks launching one: still give the
        # user the address, which is the point of the button.
        TaskDialog.Show('About EZTable',
                        'Could not open a browser. The address is:\n\n' + url)


dialog = TaskDialog('About EZTable')
dialog.MainInstruction = 'EZTable ' + __version__
dialog.MainContent = ('Excel tables into Revit.\n\n'
                      'A free plug-in from EZbuild. It makes no network '
                      'connections and collects no personal information.')
dialog.CommonButtons = TaskDialogCommonButtons.Close
dialog.DefaultButton = TaskDialogResult.Close
dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1,
                      'Privacy policy', PRIVACY_URL)
dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2,
                      'Code signing policy', CODE_SIGNING_URL)
dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink3,
                      'Website', HOME_URL)

result = dialog.Show()
if result == TaskDialogResult.CommandLink1:
    open_url(PRIVACY_URL)
elif result == TaskDialogResult.CommandLink2:
    open_url(CODE_SIGNING_URL)
elif result == TaskDialogResult.CommandLink3:
    open_url(HOME_URL)
