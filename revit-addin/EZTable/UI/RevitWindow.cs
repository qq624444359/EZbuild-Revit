using System;
using System.Windows;
using System.Windows.Interop;

namespace EZTable.UI
{
    /// <summary>
    /// Ties the add-in's dialogs to Revit's main window.
    ///
    /// A modal dialog with no owner is a free-standing top-level window. Revit
    /// is blocked while it is open, but nothing keeps the dialog in front: it can
    /// open behind Revit, or on another screen, and Revit then looks frozen with
    /// no visible way out. That is the likely cause of the freeze Autodesk's
    /// marketplace review reported right after a workbook was picked -- the
    /// moment the worksheet picker opens. An owned dialog always stays above its
    /// owner, opens centred on it, and needs no taskbar button of its own.
    /// </summary>
    internal static class RevitWindow
    {
        /// <summary>Make Revit the owner of a WPF dialog. Call before
        /// ShowDialog. A zero handle (no main window) leaves the dialog
        /// free-standing, centred on the screen, as before.</summary>
        public static T OwnedBy<T>(this T dialog, IntPtr revitWindow) where T : Window
        {
            if (revitWindow == IntPtr.Zero)
            {
                dialog.WindowStartupLocation = WindowStartupLocation.CenterScreen;
                return dialog;
            }
            new WindowInteropHelper(dialog).Owner = revitWindow;
            dialog.WindowStartupLocation = WindowStartupLocation.CenterOwner;
            dialog.ShowInTaskbar = false;
            return dialog;
        }

        /// <summary>The same handle, for WinForms dialogs such as
        /// OpenFileDialog.ShowDialog(owner).</summary>
        public sealed class Handle : System.Windows.Forms.IWin32Window
        {
            public Handle(IntPtr handle) { this.handle = handle; }
            private readonly IntPtr handle;
            IntPtr System.Windows.Forms.IWin32Window.Handle => handle;
        }
    }
}
