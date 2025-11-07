from mesmerglass.cli import compare_vmc_launcher


def test_compare_vmc_launcher_monotonic_pred_director_vs_director():
    # Use director for both to avoid timer variance; predictions should decrease as x increases
    xs = [4, 6, 8, 10]
    rows = compare_vmc_launcher(xs, delta_deg=90.0, launcher_mode="director", ceil_frame=True)
    preds = [r["vmc_predicted"] for r in rows]
    # vmc_predicted equals predicted_seconds (60 FPS-based) and should be non-increasing
    assert all(preds[i] >= preds[i+1] for i in range(len(preds)-1))
