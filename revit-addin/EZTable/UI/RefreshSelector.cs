using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Button = System.Windows.Controls.Button;
using Brushes = System.Windows.Media.Brushes;
using HorizontalAlignment = System.Windows.HorizontalAlignment;
using ListBox = System.Windows.Controls.ListBox;
using Orientation = System.Windows.Controls.Orientation;
using SelectionMode = System.Windows.Controls.SelectionMode;
using FontFamily = System.Windows.Media.FontFamily;

namespace EZTable.UI
{
    /// <summary>
    /// Picks which tables to refresh. Multi-select, with the changed ones
    /// selected by default.
    /// </summary>
    public class RefreshSelector : Window
    {
        /// <summary>
        /// A list row. It carries its index directly rather than looking the
        /// display text back up: should two rows ever read the same, IndexOf
        /// would map both to the same entry.
        /// </summary>
        public class Row
        {
            public int Index { get; }
            public string Text { get; }

            public Row(int index, string text)
            {
                Index = index;
                Text = text;
            }

            // ListBox displays items via ToString() by default
            public override string ToString() { return Text; }
        }

        public List<int> SelectedIndices { get; private set; } = new List<int>();

        /// <param name="rows">The rows, each carrying its index</param>
        /// <param name="preselect">Row numbers selected by default (the changed ones)</param>
        public RefreshSelector(List<Row> rows, IEnumerable<int> preselect)
        {
            Title = "Select the tables to refresh";
            Width = 620;
            Height = 420;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            Background = Brushes.White;

            var grid = new Grid { Margin = new Thickness(15) };
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

            var label = new TextBlock
            {
                Text = "Tables already up to date are skipped automatically.",
                Margin = new Thickness(0, 0, 0, 10),
                FontSize = 13
            };
            Grid.SetRow(label, 0);
            grid.Children.Add(label);

            var listBox = new ListBox
            {
                ItemsSource = rows,
                SelectionMode = SelectionMode.Extended,
                FontFamily = new FontFamily("Consolas, Courier New"),
                FontSize = 12
            };
            Grid.SetRow(listBox, 1);
            grid.Children.Add(listBox);

            var preset = new HashSet<int>(preselect ?? Enumerable.Empty<int>());
            listBox.Loaded += (s, e) =>
            {
                foreach (Row row in rows)
                    if (preset.Contains(row.Index))
                        listBox.SelectedItems.Add(row);
                if (listBox.SelectedItems.Count == 0 && rows.Count > 0)
                    listBox.SelectedIndex = 0;
            };

            var btnPanel = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 15, 0, 0)
            };
            Grid.SetRow(btnPanel, 2);

            var btnAll = new Button
            {
                Content = "Select All",
                Width = 90,
                Height = 30,
                Margin = new Thickness(0, 0, 10, 0)
            };
            btnAll.Click += (s, e) => listBox.SelectAll();
            btnPanel.Children.Add(btnAll);

            var btnOk = new Button
            {
                Content = "Refresh",
                Width = 90,
                Height = 30,
                Margin = new Thickness(0, 0, 10, 0),
                IsDefault = true
            };
            btnOk.Click += (s, e) =>
            {
                SelectedIndices = listBox.SelectedItems
                    .Cast<Row>()
                    .Select(row => row.Index)
                    .Distinct()
                    .OrderBy(i => i)
                    .ToList();
                DialogResult = true;
                Close();
            };
            btnPanel.Children.Add(btnOk);

            var btnCancel = new Button
            {
                Content = "Cancel",
                Width = 90,
                Height = 30,
                IsCancel = true
            };
            btnCancel.Click += (s, e) =>
            {
                DialogResult = false;
                Close();
            };
            btnPanel.Children.Add(btnCancel);

            grid.Children.Add(btnPanel);
            Content = grid;
        }
    }
}
