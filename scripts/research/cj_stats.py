import sys, numpy as np, pandas as pd, pyreadr
d=sys.argv[1]
t=pyreadr.read_r(d+'/transactions.rds')[None]
t['date']=t['transaction_timestamp'].dt.normalize()
b=t.groupby(['household_id','basket_id']).agg(v=('sales_value','sum'),date=('date','min'),cd=('coupon_disc','sum')).reset_index()
b=b[b.v>0]
H=b.household_id.nunique(); start,end=b.date.min(),b.date.max(); weeks=((end-start).days+1)/7
print("households",H,"baskets",len(b),"span",start.date(),end.date(),"weeks %.1f"%weeks)
# trips per household per week (distinct basket)
tp=b.groupby('household_id').size()/weeks
print("baskets/hh/week mean %.2f median %.2f p10 %.2f p90 %.2f CV %.3f gamma_shape %.2f"%(tp.mean(),tp.median(),tp.quantile(.1),tp.quantile(.9),tp.std()/tp.mean(),(tp.mean()/tp.std())**2))
# basket value
lv=np.log(b.v)
print("basket value $ median %.2f mean %.2f p10 %.2f p90 %.2f ln-sd(all baskets) %.3f"%(b.v.median(),b.v.mean(),b.v.quantile(.1),b.v.quantile(.9),lv.std()))
hm=b.groupby('household_id').v.median(); print("hh median basket: median %.2f ln-sd across hh %.3f"%(hm.median(),np.log(hm).std()))
within=b.assign(lv=lv).groupby('household_id').lv.std().median(); print("within-hh ln-sd median %.3f"%within)
hmean=b.groupby('household_id').v.mean(); print("hh mean basket CV across hh %.3f"%(hmean.std()/hmean.mean()))
# big baskets only (>= $20) proxy for stock-up/online-like orders
bb=b[b.v>=20]; print("baskets>=$20 share %.3f median %.2f ln-sd %.3f"%(len(bb)/len(b),bb.v.median(),np.log(bb.v).std()))
# gaps between distinct shopping days
days=b[['household_id','date']].drop_duplicates().sort_values(['household_id','date'])
days['gap']=days.groupby('household_id').date.diff().dt.days
g=days.gap.dropna()
print("gap(days between shopping days) mean %.2f median %.0f p75 %.0f p90 %.0f p95 %.0f p99 %.0f"%(g.mean(),g.median(),g.quantile(.75),g.quantile(.9),g.quantile(.95),g.quantile(.99)))
for k in (28,42,60,90): print("share gaps >= %d: %.4f ; hh with any gap>=%d: %.3f"%(k,(g>=k).mean(),k,(days.groupby('household_id').gap.max()>=k).mean()))
hg=days.groupby('household_id').gap.mean().dropna(); print("hh mean gap median %.2f ln-sd %.3f"%(hg.median(),np.log(hg).std()))
# big-basket trips gaps (>= $20) as online-like stock-up cycle
bd=bb[['household_id','date']].drop_duplicates().sort_values(['household_id','date']); bd['gap']=bd.groupby('household_id').date.diff().dt.days
gb=bd.gap.dropna(); print("gap between >=$20 trips mean %.2f median %.0f p90 %.0f p95 %.0f"%(gb.mean(),gb.median(),gb.quantile(.9),gb.quantile(.95)))
# end-of-data inactivity
last=days.groupby('household_id').date.max(); inact=(end-last).dt.days
for k in (28,42,60,90): print("hh inactive >= %d days at data end: %.3f"%(k,(inact>=k).mean()))
# first-half active, second-half lapsed (churn-like)
mid=start+pd.Timedelta(days=182)
h1=set(b[b.date<mid].household_id); q4=set(b[b.date>=end-pd.Timedelta(days=41)].household_id)
print("hh active in H1: %d ; of those no purchase in last 42 days: %.3f"%(len(h1),1-len(h1&q4)/len(h1)))
# pareto
s=b.groupby('household_id').v.sum().sort_values(ascending=False); top=int(.2*len(s))
print("top20%% hh share of sales %.3f ; top10%% %.3f"%(s.iloc[:top].sum()/s.sum(), s.iloc[:int(.1*len(s))].sum()/s.sum()))
# coupons
c=pyreadr.read_r(d+'/campaigns.rda')['campaigns']; cr=pyreadr.read_r(d+'/coupon_redemptions.rda')['coupon_redemptions']; cdsc=pyreadr.read_r(d+'/campaign_descriptions.rda')['campaign_descriptions']
pairs=c.drop_duplicates(); red=cr[['household_id','campaign_id']].drop_duplicates()
m=pairs.merge(red.assign(r=1),on=['household_id','campaign_id'],how='left').fillna({'r':0})
print("targeted hh-campaign pairs %d ; redeemed>=1 coupon: %.4f ; targeted hh %d ; hh redeemed any %.4f"%(len(m),m.r.mean(),pairs.household_id.nunique(), cr.household_id.nunique()/pairs.household_id.nunique()))
m2=m.merge(cdsc[['campaign_id','campaign_type']],on='campaign_id'); print(m2.groupby('campaign_type',observed=True).r.agg(['mean','size']).to_string())
print("baskets with coupon_disc<0 or >0 share: %.4f"%((b.cd!=0).mean()))
