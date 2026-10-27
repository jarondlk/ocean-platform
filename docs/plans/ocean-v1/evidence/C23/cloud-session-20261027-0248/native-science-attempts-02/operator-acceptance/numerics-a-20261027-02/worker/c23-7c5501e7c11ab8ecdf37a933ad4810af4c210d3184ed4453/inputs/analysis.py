# Operator-owned synthetic acceptance: numerics-a; nonce=4a4f4ceafa7445eb90ac55c6e4300bfa
INPUT_MACHINE='table-01.json'
HOST_CANARY='/var/lib/ocean-c23/operator-acceptance/numerics-a-20261027-02/host-canary.txt'
HOST_SOCKET='/var/lib/ocean-c23/operator-acceptance/numerics-a-20261027-02/host.sock'
def write_summary(rows):
 import json
 with open("summary.json","w",encoding="utf-8") as stream:
  json.dump({"columns":["probe","value"],"rows":rows},stream,ensure_ascii=False,allow_nan=False,separators=(",",":"))
import json,math
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.stats as stats
import statsmodels.api as sm
exact = json.load(open('/inputs/'+INPUT_MACHINE))['operator_int64_probe']
frame = pd.DataFrame({'exact':np.asarray(exact,dtype=np.int64)})
pq.write_table(pa.Table.from_pandas(frame,preserve_index=False),'/scratch/exact.parquet')
restored = pq.read_table('/scratch/exact.parquet').column('exact').to_pylist()
assert restored == exact and restored[-1] == 9223372036854775807
rng = np.random.default_rng(20261024)
values = rng.normal(size=32)
test = stats.ttest_1samp(values,0.0)
fit = sm.OLS(np.array([1.,3.,5.,7.]),sm.add_constant(np.arange(4,dtype=float))).fit()
assert math.isclose(float(fit.params[0]),1.,rel_tol=1e-10,abs_tol=1e-10)
assert math.isclose(float(fit.params[1]),2.,rel_tol=1e-10,abs_tol=1e-10)
assert all(math.isfinite(float(value)) for value in [values.mean(),test.statistic,test.pvalue])
write_summary([['mean',float(values.mean())],['t_statistic',float(test.statistic)],
               ['p_value',float(test.pvalue)],['ols_intercept',float(fit.params[0])],
               ['ols_slope',float(fit.params[1])],['exact_int64',restored[-1]]])
