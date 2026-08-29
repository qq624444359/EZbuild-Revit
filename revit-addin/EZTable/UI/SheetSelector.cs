using System;
using System.Collections.Generic;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using ComboBox = System.Windows.Controls.ComboBox;
using Orientation = System.Windows.Controls.Orientation;
using Button = System.Windows.Controls.Button;
using Brushes = System.Windows.Media.Brushes;
using HorizontalAlignment = System.Windows.HorizontalAlignment;
using VerticalAlignment = System.Windows.VerticalAlignment;

namespace EZTable.UI
{
    public class SheetSelector : Window
    {
        public string SelectedSheet { get; private set; }

        public SheetSelector(List<string> sheetNames)
        {
            Title = "Select Worksheet to Import";
            Width = 350;
            Height = 180;
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
            ResizeMode = ResizeMode.NoResize;
            Background = Brushes.White;

            var grid = new Grid { Margin = new Thickness(15) };
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

            var label = new TextBlock
            {
                Text = "Please select the worksheet to import:",
                Margin = new Thickness(0, 0, 0, 10),
                FontSize = 14
            };
            Grid.SetRow(label, 0);
            grid.Children.Add(label);

            var comboBox = new ComboBox
            {
                ItemsSource = sheetNames,
                SelectedIndex = 0,
                Height = 28,
                FontSize = 14,
                VerticalContentAlignment = VerticalAlignment.Center
            };
            Grid.SetRow(comboBox, 1);
            grid.Children.Add(comboBox);

            var btnPanel = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 15, 0, 0)
            };
            Grid.SetRow(btnPanel, 2);

            var btnOk = new Button
            {
                Content = "Import",
                Width = 80,
                Height = 30,
                Margin = new Thickness(0, 0, 10, 0),
                IsDefault = true
            };
            btnOk.Click += (s, e) =>
            {
                SelectedSheet = comboBox.SelectedItem as string;
                DialogResult = true;
                Close();
            };
            btnPanel.Children.Add(btnOk);

            var btnCancel = new Button
            {
                Content = "Cancel",
                Width = 80,
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

