# Authentic synthetic C22 owner review; experimental, not scientific approval.
import json, math
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.stats as stats
import statsmodels.api as sm
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
exact=[9223372036854775806,9223372036854775807]
frame=pd.DataFrame({"exact":np.asarray(exact,dtype=np.int64)})
pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),"/scratch/exact.parquet")
restored=pq.read_table("/scratch/exact.parquet").column("exact").to_pylist()
assert restored==exact
values=np.random.default_rng(20261024).normal(size=32)
test=stats.ttest_1samp(values,0.0)
fit=sm.OLS(np.array([1.,3.,5.,7.]),sm.add_constant(np.arange(4,dtype=float))).fit()
assert math.isclose(float(fit.params[0]),1.,rel_tol=1e-10,abs_tol=1e-10)
assert math.isclose(float(fit.params[1]),2.,rel_tol=1e-10,abs_tol=1e-10)
fig,ax=plt.subplots(figsize=(2,2));ax.plot([0,1],[0,1]);fig.savefig("/scratch/probe.png");plt.close(fig)
assert open("/scratch/probe.png","rb").read(8)==b"\x89PNG\r\n\x1a\n"
rows=[["mean",float(values.mean())],["t_statistic",float(test.statistic)],["p_value",float(test.pvalue)],
      ["ols_intercept",float(fit.params[0])],["ols_slope",float(fit.params[1])],["exact_int64",restored[-1]]]
assert all(math.isfinite(value) for name,value in rows)
with open("summary.json","w",encoding="utf-8") as stream:
    json.dump({"columns":["probe","value"],"rows":rows},stream,allow_nan=False,separators=(",",":"))
