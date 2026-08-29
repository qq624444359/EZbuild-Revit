using System;
using Autodesk.Revit.UI;
using Autodesk.Revit.DB;
using System.Windows.Media.Imaging;

namespace EZTable
{
    public class App : IExternalApplication
    {
        public Result OnStartup(UIControlledApplication application)
        {
            // 1. Create our own ribbon tab
            string tabName = "EZbuild";
            try
            {
                application.CreateRibbonTab(tabName);
            }
            catch (Autodesk.Revit.Exceptions.ArgumentException)
            {
                // Revit throws when the tab already exists; ignoring that is fine
            }

            // 2. Create a panel under the tab
            RibbonPanel panel = application.CreateRibbonPanel(tabName, "Table");

            // 3. Build the button data
            string thisAssemblyPath = System.Reflection.Assembly.GetExecutingAssembly().Location;
            
            PushButtonData btnImportData = new PushButtonData(
                "cmdImportExcel",
                "Import Excel",
                thisAssemblyPath,
                "EZTable.Commands.CmdImport")
            {
                ToolTip = "Import Excel worksheet to a Drafting View.",
                LargeImage = LoadImage("Import.png"),
                Image = LoadImage("Import.png", 16)
            };

            PushButtonData btnRefreshData = new PushButtonData(
                "cmdRefreshExcel",
                "Refresh",
                thisAssemblyPath,
                "EZTable.Commands.CmdRefresh")
            {
                ToolTip = "Re-read the source Excel files and redraw the tables that changed. " +
                          "View ids are preserved, so viewports already placed on sheets stay valid.",
                LargeImage = LoadImage("Refresh.png"),
                Image = LoadImage("Refresh.png", 16)
            };

            PushButtonData btnCleanupData = new PushButtonData(
                "cmdCleanupExcel",
                "Cleanup",
                thisAssemblyPath,
                "EZTable.Commands.CmdCleanup")
            {
                ToolTip = "Delete leftover EZ_* and XL_* text types, filled region types, line styles and line patterns that no element uses any more.",
                LargeImage = LoadImage("Cleanup.png"),
                Image = LoadImage("Cleanup.png", 16)
            };

            // 4. Add the buttons to the panel
            panel.AddItem(btnImportData);
            
            // Stack the auxiliary functions (Refresh and Cleanup) so they appear smaller
            panel.AddStackedItems(btnRefreshData, btnCleanupData);

            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            return Result.Succeeded;
        }

        private System.Windows.Media.ImageSource LoadImage(string name, int size = 32)
        {
            try
            {
                var stream = System.Reflection.Assembly.GetExecutingAssembly()
                    .GetManifestResourceStream("EZTable.Resources." + name);
                if (stream == null) return null;

                var bitmap = new BitmapImage();
                bitmap.BeginInit();
                bitmap.StreamSource = stream;
                bitmap.DecodePixelWidth = size;
                bitmap.DecodePixelHeight = size;
                bitmap.EndInit();
                return bitmap;
            }
            catch
            {
                return null;
            }
        }
    }
}
