import csv, sys, math, statistics as st
from collections import defaultdict
orders_path, train_path = sys.argv[1], sys.argv[2]
gaps=[]; user_gaps=defaultdict(list); user_n=defaultdict(int); hist=defaultdict(int)
with open(orders_path, newline='') as f:
    r=csv.DictReader(f)
    for row in r:
        u=row['user_id']; user_n[u]+=1
        d=row['days_since_prior_order']
        if d!='':
            v=float(d); gaps.append(v); user_gaps[u].append(v); hist[int(v)]+=1
n=len(gaps); gaps.sort()
def q(p): return gaps[int(p*(n-1))]
mean=sum(gaps)/n; sd=st.pstdev(gaps)
print("orders_rows", sum(user_n.values()), "users", len(user_n), "gaps_n", n)
print("gap mean %.3f sd %.3f p10 %s p25 %s p50 %s p75 %s p90 %s"%(mean,sd,q(.1),q(.25),q(.5),q(.75),q(.9)))
for k in (0,1,7,14,21,30): print("share gap==%d: %.4f"%(k,hist[k]/n))
print("share gap<=7: %.4f"%(sum(hist[k] for k in range(0,8))/n))
print("share gap>=28: %.4f"%(sum(hist[k] for k in range(28,31))/n))
print("share gap>=21: %.4f"%(sum(hist[k] for k in range(21,31))/n))
# orders per user
cnt=sorted(user_n.values())
print("orders/user min %d p25 %d median %d mean %.2f p75 %d max %d"%(cnt[0],cnt[len(cnt)//4],cnt[len(cnt)//2],sum(cnt)/len(cnt),cnt[3*len(cnt)//4],cnt[-1]))
cd=sorted(cnt, reverse=True); top=int(0.2*len(cd))
print("top20%% users share of orders: %.4f"%(sum(cd[:top])/sum(cd)))
# per-user mean gap heterogeneity (users with >=3 gaps)
um=[sum(g)/len(g) for u,g in user_gaps.items() if len(g)>=3]
um.sort(); m=len(um)
print("users>=3gaps", m, "user-mean-gap p10 %.2f p25 %.2f p50 %.2f p75 %.2f p90 %.2f mean %.2f"%(um[int(.1*m)],um[int(.25*m)],um[int(.5*m)],um[int(.75*m)],um[int(.9*m)],sum(um)/m))
lg=[math.log(max(x,0.5)) for x in um]
print("sd of ln(user mean gap): %.3f"%st.pstdev(lg))
rates=[1/max(x,0.5) for x in um]; mr=sum(rates)/len(rates); cv=st.pstdev(rates)/mr
print("CV of user order rate (1/mean gap): %.3f -> gamma shape approx %.2f"%(cv, 1/cv**2))
# within-user CV of gaps
wcv=[]
for u,g in user_gaps.items():
    if len(g)>=5:
        mu=sum(g)/len(g)
        if mu>0: wcv.append(st.pstdev(g)/mu)
wcv.sort(); print("within-user gap CV median %.3f (users>=5 gaps n=%d)"%(wcv[len(wcv)//2], len(wcv)))
print("hist", {k:round(hist[k]/n,4) for k in range(31)})
# reorder
tot=0; re=0; orders=set()
with open(train_path, newline='') as f:
    for row in csv.DictReader(f):
        tot+=1; re+=int(row['reordered']); orders.add(row['order_id'])
print("train lines", tot, "orders", len(orders), "reordered share %.4f items/order %.2f"%(re/tot, tot/len(orders)))
