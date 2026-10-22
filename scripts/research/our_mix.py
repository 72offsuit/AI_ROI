import json, sys, numpy as np
c=json.load(open(sys.argv[1])); rng=np.random.default_rng(42); N=26000
ids=[p['id'] for p in c['personas']]; w=np.array([p['ratio_bp'] for p in c['personas']])/1e4
T={t['name']:t for t in c['hidden_traits']}
pid=rng.choice(len(ids),size=N,p=w)
def beta(name):
    t=T[name]; k=t['kappa_milli']/1000; mu=np.array([t['mu_ppm'][i]/1e6 for i in ids])[pid]; return rng.beta(mu*k,(1-mu)*k)
def ln(name):
    t=T[name]; s=t['sigma_ppm']/1e6; med=np.array([t['median'][i] for i in ids])[pid]; return med*np.exp(s*rng.standard_normal(N))
vt=T['base_visit_frequency']; k=vt['shape_milli']/1000; m=np.array([vt['mean'][i]/1000 for i in ids])[pid]; visit=rng.gamma(k,m/k)
pp=beta('base_purchase_probability'); aov=ln('base_order_value'); cyc=ln('purchase_cycle')/1000
rate=visit*pp*30/7
print("visit/wk mean %.2f CV %.3f shape_eq %.2f"%(visit.mean(),visit.std()/visit.mean(),(visit.mean()/visit.std())**2))
print("purchase prob per visit mean %.3f"%pp.mean())
print("orders/month (visit*p) mean %.2f median %.2f CV %.3f gamma_shape_eq %.2f"%(rate.mean(),np.median(rate),rate.std()/rate.mean(),(rate.mean()/rate.std())**2))
print("AOV mean %.0f median %.0f ln-sd(mixture) %.3f CV %.3f"%(aov.mean(),np.median(aov),np.log(aov).std(),aov.std()/aov.mean()))
print("cycle median %.1f mean %.1f ln-sd(mixture) %.3f p90 %.1f"%(np.median(cyc),cyc.mean(),np.log(cyc).std(),np.quantile(cyc,.9)))
spend=rate*aov; s=np.sort(spend)[::-1]; print("top20%% spend share %.3f top10%% %.3f"%(s[:N//5].sum()/s.sum(), s[:N//10].sum()/s.sum()))
cnt=np.sort(rate)[::-1]; print("top20%% order-count share %.3f"%(cnt[:N//5].sum()/cnt.sum()))
for n in ['base_churn_propensity','coupon_sensitivity','marketing_fatigue','cart_abandonment_propensity','repurchase_propensity','price_sensitivity','shipping_fee_sensitivity']:
    x=beta(n); print(n,"pop mean %.3f"%x.mean())
f=beta('marketing_fatigue'); print("P(fatigue>0.6) %.4f"%(f>0.6).mean())
print("share customers orders/month >= 4.33 (weekly+): %.3f ; >=1/month: %.3f ; <0.5/month: %.3f"%((rate>=4.33).mean(),(rate>=1).mean(),(rate<0.5).mean()))
for i,p in enumerate(ids): 
    m=pid==i; print(p, "orders/mo mean %.2f AOV med %.0f"%(rate[m].mean(), np.median(aov[m])))
tot=spend.sum()
for i,p in enumerate(ids): print("spend share", p, "%.3f"%(spend[pid==i].sum()/tot))
