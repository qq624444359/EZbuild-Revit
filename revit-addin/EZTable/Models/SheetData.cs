using System;
using System.Collections.Generic;

namespace EZTable.Models
{
    public class SheetData
    {
        public string SheetName { get; set; }
        public List<CellModel> Cells { get; set; } = new List<CellModel>();
        public Dictionary<int, double> RowHeightsFt { get; set; } = new Dictionary<int, double>();
        public Dictionary<int, double> ColWidthsFt { get; set; } = new Dictionary<int, double>();
        public List<string> Warnings { get; set; } = new List<string>();
    }
}
