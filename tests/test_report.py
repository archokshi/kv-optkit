import pandas as pd
from pathlib import Path
from tools.make_report import generate_report


def test_report_from_csv(tmp_path: Path):
    csv = tmp_path/"metrics.csv"
    # Create simple before/after dataset
    df = pd.DataFrame({
        "hbm_gb": [100, 98, 80, 78],
        "ddr_gb": [0.0, 0.0, 2.0, 2.5],
        "p95_ms": [2100, 2050, 1900, 1850],
        "ttft_s": [12.0, 11.8, 5.0, 4.5],
        # counters (monotonic)
        "evicted": [0, 0, 5, 7],
        "quantized": [0, 1, 3, 5],
        "reuse_hits": [10, 12, 15, 20],
        "reuse_misses": [2, 2, 3, 3],
        "applies": [0, 1, 2, 3],
        "rollbacks": [0, 0, 0, 1],
    })
    df.to_csv(csv, index=False)

    out = tmp_path/"run_report.md"
    generate_report("file", out, csv_path=csv)

    # Assertions: report exists and references charts
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "KV-OptKit Run Report" in text
    # charts should be generated in outputs/charts/
    charts_dir = Path("outputs/charts")
    assert (charts_dir/"hbm.png").exists()
    assert (charts_dir/"latency.png").exists()
    assert (charts_dir/"ttft.png").exists()
    assert (charts_dir/"ddr.png").exists()
    # Summary contains DDR and Action Counters
    assert "DDR before" in text
    assert "Action Counters" in text
