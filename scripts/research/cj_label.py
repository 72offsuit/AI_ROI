import sys, pandas as pd, pyreadr
t=pyreadr.read_r(sys.argv[1]+'/transactions.rds')[None]
t['date']=t['transaction_timestamp'].dt.normalize()
d=t[t.sales_value>0][['household_id','date']].drop_duplicates()
for T0s in ('2017-07-01','2017-09-01','2017-11-01'):
    T0=pd.Timestamp(T0s)
    pre=d[(d.date<T0)&(d.date>=T0-pd.Timedelta(days=180))]
    elig=set(pre.household_id)
    last=pre.groupby('household_id').date.max()
    post=set(d[(d.date>=T0)&(d.date<T0+pd.Timedelta(days=42))].household_id)
    churn=1-len(elig&post)/len(elig)
    e14=set(last[(T0-last).dt.days>=14].index)
    churn14=1-len(e14&post)/len(e14) if e14 else float('nan')
    print("T0 %s eligible(180d active) %d churn42 %.3f | subset last purchase>=14d ago n=%d churn42 %.3f"%(T0s,len(elig),churn,len(e14),churn14))
