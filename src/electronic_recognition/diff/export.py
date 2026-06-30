"""
M1: Export CATDrawing to PDF via pycatia (CATIA COM Automation).
Also supports DWG -> PDF via AutoCAD COM.

Usage:
    python export_catdrawing.py raw.CATDrawing -o input/raw.pdf
    python export_catdrawing.py M-T1-02.dwg -o input/M-T1-02.pdf --type dwg
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def export_catdrawing_pycatia(source: Path, output: Path) -> dict:
    """Export a .CATDrawing file to PDF using pycatia (CATIA COM)."""
    log = {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "tool": "pycatia",
        "tool_version": None,
        "export_time": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "pages": 0,
        "page_size": None,
        "orientation": None,
    }

    try:
        import pycatia
        from pycatia import catia

        log["tool_version"] = pycatia.__version__

        caa = catia()
        if caa is None:
            log["error"] = "Cannot connect to CATIA COM. Is CATIA running?"
            return log

        documents = caa.documents
        drawing_doc = documents.open(str(source.resolve()))
        drawing_sheets = drawing_doc.sheets
        log["pages"] = drawing_sheets.count

        drawing_doc.export_data(output.resolve(), "pdf", overwrite=True)

        drawing_doc.close()

        if output.exists() and output.stat().st_size > 0:
            log["success"] = True
        else:
            log["error"] = "Export produced no output file or zero-size file."

    except ImportError:
        log["error"] = "pycatia not installed. Run: pip install pycatia"
    except Exception as e:
        log["error"] = str(e)

    return log


def export_dwg_autocad(source: Path, output: Path) -> dict:
    """Export a .dwg file to PDF using AutoCAD COM Automation."""
    log = {
        "source": str(source.resolve()),
        "output": str(output.resolve()),
        "tool": "AutoCAD COM",
        "tool_version": None,
        "export_time": datetime.now().isoformat(),
        "success": False,
        "error": None,
        "pages": 0,
        "page_size": None,
        "orientation": None,
    }

    try:
        import win32com.client

        acad = win32com.client.Dispatch("AutoCAD.Application")
        log["tool_version"] = acad.Version

        doc = acad.Documents.Open(str(source.resolve()))

        layouts = doc.Layouts
        log["pages"] = layouts.Count

        plot_cfg = acad.ActiveDocument.PlotConfigurations.Add("TEMP_PC3", "DWG To PDF.pc3")

        layout = doc.ActiveLayout
        layout.RefreshPlotDeviceInfo()
        layout.ConfigName = "DWG To PDF.pc3"
        layout.PlotType = 1  # acExtents
        layout.PlotRotation = 0  # ac0degrees
        layout.StandardScale = 0  # acScaleToFit
        layout.CenterPlot = True
        layout.PlotWithPlotStyles = True

        result = doc.Plot.PlotToFile(str(output.resolve()), "DWG To PDF.pc3")
        log["success"] = result

        doc.Close(False)

        if output.exists() and output.stat().st_size > 0:
            log["success"] = True
        else:
            log["error"] = "Export produced no output file or zero-size file."

    except ImportError:
        log["error"] = "pywin32 not installed, required for AutoCAD COM. Run: pip install pywin32"
    except Exception as e:
        log["error"] = str(e)

    return log


def main():
    parser = argparse.ArgumentParser(description="Export CAD drawing to PDF")
    parser.add_argument("source", type=Path, help="Source .CATDrawing or .dwg file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output PDF path")
    parser.add_argument(
        "--type",
        choices=["catdrawing", "dwg", "auto"],
        default="auto",
        help="Source file type (default: auto-detect)",
    )
    parser.add_argument("--log", type=Path, default=None, help="Export log output path")
    args = parser.parse_args()

    source = args.source
    if not source.exists():
        print(f"Error: source file not found: {source}", file=sys.stderr)
        sys.exit(1)

    ext = source.suffix.lower()
    if args.type == "auto":
        if ext == ".catdrawing":
            file_type = "catdrawing"
        elif ext == ".dwg":
            file_type = "dwg"
        else:
            print(f"Error: cannot auto-detect type for extension: {ext}", file=sys.stderr)
            sys.exit(1)
    else:
        file_type = args.type

    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)

    if file_type == "catdrawing":
        log = export_catdrawing_pycatia(source, output)
    else:
        log = export_dwg_autocad(source, output)

    log_path = args.log or output.with_suffix(".export_log.json")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    if log["success"]:
        print(f"Export OK: {source} -> {output}")
    else:
        print(f"Export FAILED: {log['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
