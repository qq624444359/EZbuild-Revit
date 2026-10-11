using System;
using System.Diagnostics;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using TaskDialog = Autodesk.Revit.UI.TaskDialog;

namespace EZTable.Commands
{
    /// <summary>
    /// About -- the version, and links to the privacy and code signing policies.
    ///
    /// The Autodesk marketplace requires the privacy policy to be reachable from
    /// inside the app, not only from the store listing, so this button exists
    /// mainly to carry that link. It changes nothing in the document.
    ///
    /// The pyRevit edition's About.pushbutton shows the same dialog; keep the two
    /// in step.
    /// </summary>
    [Transaction(TransactionMode.ReadOnly)]
    public class CmdAbout : IExternalCommand
    {
        public const string PrivacyUrl = "https://www.ezbuild.co.nz/for-revit-privacy.html";
        public const string CodeSigningUrl = "https://www.ezbuild.co.nz/code-signing.html";
        public const string HomeUrl = "https://www.ezbuild.co.nz/for-revit.html";

        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            // AppVersion from PackageContents.xml, stamped into the assembly at build time
            Version v = System.Reflection.Assembly.GetExecutingAssembly().GetName().Version;
            string version = v.Major + "." + v.Minor + "." + v.Build;

            var dialog = new TaskDialog("About EZTable")
            {
                MainInstruction = "EZTable " + version,
                MainContent = "Excel tables into Revit.\n\n" +
                              "A free plug-in from EZbuild. It makes no network connections " +
                              "and collects no personal information.",
                CommonButtons = TaskDialogCommonButtons.Close,
                DefaultButton = TaskDialogResult.Close,
            };
            dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, "Privacy policy", PrivacyUrl);
            dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, "Code signing policy", CodeSigningUrl);
            dialog.AddCommandLink(TaskDialogCommandLinkId.CommandLink3, "Website", HomeUrl);

            string url;
            switch (dialog.Show())
            {
                case TaskDialogResult.CommandLink1: url = PrivacyUrl; break;
                case TaskDialogResult.CommandLink2: url = CodeSigningUrl; break;
                case TaskDialogResult.CommandLink3: url = HomeUrl; break;
                default: return Result.Succeeded;
            }

            try
            {
                // UseShellExecute: on .NET 8 and 10 a bare URL is not an executable
                Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
            }
            catch (Exception)
            {
                // No default browser, or a policy blocks launching one: still give
                // the user the address, which is the point of the button.
                TaskDialog.Show("About EZTable", "Could not open a browser. The address is:\n\n" + url);
            }
            return Result.Succeeded;
        }
    }

    /// <summary>
    /// Keeps a button enabled even with no document open. Revit disables add-in
    /// buttons on the start screen by default, and About should be reachable
    /// before anything is opened.
    /// </summary>
    public class AlwaysAvailable : IExternalCommandAvailability
    {
        public bool IsCommandAvailable(UIApplication applicationData, CategorySet selectedCategories)
        {
            return true;
        }
    }
}
