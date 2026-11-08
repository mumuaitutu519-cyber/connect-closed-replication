from common import *
import pyarrow.dataset as ds
from scipy.stats import t as student_t
def describe(v):
 v=pd.Series(v).replace([np.inf,-np.inf],np.nan).dropna();q=v.quantile([.25,.5,.75]);return dict(Obs=len(v),Mean=v.mean(),SD=v.std(),Min=v.min(),P25=q.loc[.25],Median=q.loc[.5],P75=q.loc[.75],Max=v.max())
def run():
 from prepare import holding_dates_audit
 holding_dates_audit()
 features=pd.read_parquet(T/'features.parquet');cols=['code','date','event_id','closed','dose','eligible',*[m+s for m in METRICS for s in ['', '__w01','__w005']]];f=ds.dataset(T/'panel',format='parquet').to_table(columns=cols,use_threads=False).to_pandas(use_threads=False);f.code=pd.Categorical(f.code);features=features[features.code.isin(f.code.cat.categories)].copy();features.code=pd.Categorical(features.code,categories=f.code.cat.categories);ff=features[['code','event_id','qfii__raw','qfii__w01','qfii__w005','logamount','logcap','ifbeta','predelay','analyst','intl_share']];f=f.merge(ff,on=['code','event_id'],how='left',validate='m:1');rows=[];counts=[]
 from scipy.stats import skew,kurtosis
 diagnostics=[]
 for variant in ['raw','w01','w005']:
  for m in METRICS:
   col=m if variant=='raw' else m+'__'+variant;v=f.loc[f.dose.notna(),col].replace([np.inf,-np.inf],np.nan).dropna();q=np.quantile(v,[.001,.01,.99,.999]);diagnostics.append(dict(metric=m,variant=variant,n=len(v),missing=len(f)-len(v),mean=v.mean(),sd=v.std(),skew=skew(v,bias=False),excess_kurtosis=kurtosis(v,bias=False),zero_share=v.eq(0).mean(),q001=q[0],q01=q[1],q99=q[2],q999=q[3]))
 save(diagnostics,'outcome_distributions.csv')
 per_event=[];events=pd.read_csv(P/'tables/events.csv',parse_dates=['start','end'])
 for ev in events.itertuples():
  z=f[f.event_id.eq(ev.event_id)];row=dict(event_id=ev.event_id,start=ev.start,end=ev.end,official_closed_days=ev.n_closed_days,panel_rows=len(z))
  for m in PRIMARY:
   ok=z.dose.notna()&z[m+'__w01'].notna();row[m+'_stock_days']=int(ok.sum());row[m+'_stocks']=z.loc[ok,'code'].nunique();row[m+'_dates']=z.loc[ok,'date'].nunique();row[m+'_closed_dates']=z.loc[ok&z.closed.eq(True),'date'].nunique()
  per_event.append(row)
 save(per_event,'sample_by_event.csv')
 reconciliation=pd.DataFrame(per_event).merge(freezes()[['event_id','freeze_date']],on='event_id',validate='1:1');reconciliation['period']=np.where(reconciliation.freeze_date.ge('2024-08-19'),'post','pre');reconciliation['estimable_if']=reconciliation.if_delay_stock_days.gt(0);reconciliation['estimable_ih']=reconciliation.ih_delay_stock_days.gt(0);save(reconciliation.groupby('period').agg(official_episodes=('event_id','size'),estimable_IF_episodes=('estimable_if','sum'),estimable_IH_episodes=('estimable_ih','sum'),IF_stock_days=('if_delay_stock_days','sum'),IH_stock_days=('ih_delay_stock_days','sum')).reset_index(),'event_count_reconciliation.csv')
 mapping_names={'if_delay':'DelayIF_x100','ih_delay':'DelayIH_x100','if_lag_sum':'LagIF_x100','ih_lag_sum':'LagIH_x100','ln_amount':'log_amount','cs_bp':'CS_bp','ar_bp':'AR_bp','amihud':'Amihud_per_billion','dose':'Hold_pp','eligible':'Eligible','qfii':'QFII_pp','hold_eligible':'Hold_eligible_only_pp'}
 for variant in ['raw','w01','w005']:
  suffix='' if variant=='raw' else '__'+variant
  vi=f.dose.notna()&f['if_delay'+suffix].notna();vh=f.dose.notna()&f['ih_delay'+suffix].notna()
  for sample,valid in [('IF_estimation',vi),('IH_estimation',vh),('IF_IH_intersection',vi&vh)]:
   wanted=['code','event_id','dose','eligible',*[m+suffix for m in METRICS],'qfii__'+variant];d=f.loc[valid,wanted].copy();counts.append(dict(variant=variant,sample=sample,stock_days=len(d),stocks=d.code.nunique(),dates=f.loc[valid,'date'].nunique(),stock_episodes=d[['code','event_id']].drop_duplicates().shape[0],events=d.event_id.nunique()))
   d=d.rename(columns={m+suffix:m for m in METRICS}|{'qfii__'+variant:'qfii'});d['hold_eligible']=d.dose.where(d.eligible.eq(1))
   for m in PRIMARY:d[m]*=100
   d['amihud']*=1000
   for grain,z in [('stock_day',d),('stock_episode',d.groupby(['event_id','code'],observed=True).mean(numeric_only=True).reset_index())]:
    for m,label in mapping_names.items():rows.append(dict(sample=sample,variant=variant,grain=grain,variable=label,**describe(z[m])))
 save(rows,'descriptive_statistics.csv');save(counts,'estimation_sample_counts.csv')
 # Balance sample = union of actual main IF and IH stock episodes, with main winsorized features.
 valid=f.dose.notna()&(f.if_delay__w01.notna()|f.ih_delay__w01.notna());keys=f.loc[valid,['event_id','code']].drop_duplicates();d=keys.merge(features,on=['event_id','code'],validate='1:1');save(d.groupby(['event_id','analyst_source']).size().reset_index(name='main_stock_episodes'),'analyst_main_sample_source.csv');save(d.groupby('event_id').agg(stock_episodes=('code','size'),intl_share_known=('intl_share','count'),intl_any_known=('intl_any','count'),h_listed_known=('h_listed','count'),foreign_first_known=('foreign_first','count')).reset_index(),'international_main_sample_coverage.csv');out=[]
 for group in ['Eligible','Positive_Hold']:
  g=d.eligible.astype(float) if group=='Eligible' else d.dose.gt(0).astype(float)
  for variant in ['raw','w01','w005']:
   for variable in ['dose','logamount','logcap','ifbeta','predelay','analyst','intl_share']:
    col=variable if variable=='dose' else variable+'__'+variant;x=d[col];ok=x.notna()&g.notna();values=x[ok].to_numpy();groups=g[ok].to_numpy();events=d.loc[ok,'event_id'].to_numpy();X=np.column_stack([np.ones(ok.sum()),groups]);row=dict(group=group,variant=variant,variable=variable,n=ok.sum(),events=len(np.unique(events)))
    if not len(values) or len(np.unique(groups))<2:row['status']='NO_COMPLETE_GROUPS';out.append(row);continue
    a=values[groups==1];b=values[groups==0];bread=np.linalg.pinv(X.T@X);coef=bread@(X.T@values);u=values-X@coef;ev,labels=pd.factorize(events);scores=np.zeros((len(labels),2))
    for j in range(2):scores[:,j]=np.bincount(ev,weights=X[:,j]*u,minlength=len(labels))
    variance=bread@(scores.T@scores)@bread*len(labels)/max(len(labels)-1,1)*(len(values)-1)/max(len(values)-2,1);se=np.sqrt(variance[1,1]);stat=coef[1]/se if se>0 else np.nan;pooled=np.sqrt((a.var(ddof=1)+b.var(ddof=1))/2)
    row.update(mean_group1=a.mean(),mean_group0=b.mean(),n_group1=len(a),n_group0=len(b),difference=coef[1],cluster_se=se,t_cluster_event=stat,p_cluster_event=2*student_t.sf(abs(stat),len(labels)-1),standardized_difference=coef[1]/pooled if pooled>0 else np.nan,status='OK');out.append(row)
 save(out,'balance_stock_episode.csv');print('DESCRIPTIVE COMPLETE',len(rows),flush=True)
if __name__=='__main__':run()
