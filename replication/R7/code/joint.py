from common import *
from inference import fit,close,legacy,plan,run
from estimate import read
from scipy.stats import t as student_t

def fieller(num,den,vnum,vden,cov,df):
 t=student_t.ppf(.975,df);A=den*den-t*t*vden;bb=-2*(num*den-t*t*cov);C=num*num-t*t*vnum;dis=bb*bb-4*A*C;ratio=num/den if den!=0 else np.nan
 if abs(A)<1e-16:
  if abs(bb)<1e-16:return ratio,'ALL_REAL'if C<=0 else'EMPTY',-np.inf,np.inf
  root=-C/bb;return ratio,'LEFT_RAY'if bb>0 else'RIGHT_RAY',root,root
 if dis<0:return ratio,'ALL_REAL'if A<0 else'EMPTY',-np.inf,np.inf
 roots=sorted([(-bb-np.sqrt(dis))/(2*A),(-bb+np.sqrt(dis))/(2*A)]);return ratio,'BOUNDED'if A>0 else'TWO_RAYS',roots[0],roots[1]

def pair(v,controls=False):
 cs=RACE+HK if controls else[];a='if_b0'if v=='raw'else'if_b0__'+v;b='if_lag_sum'if v=='raw'else'if_lag_sum__'+v;f=read(['code','date','event_id','closed','dose',a,b,*RACE,*[c+'__'+v for c in HK]]if controls else['code','date','event_id','closed','dose',a,b]);f['closed_x']=f.closed*f.dose;xs=['closed_x','dose']
 if controls:f.rename(columns={c+'__'+v:c for c in HK},inplace=True)
 for c in cs:f['cx_'+c]=f.closed*f[c];xs+=['cx_'+c,c]
 f['y']=f[a];f=f[list(dict.fromkeys(['code','date','event_id','closed','dose',a,b,'y',*xs]))];release();good=np.ones(len(f),bool)
 for c in [a,b,*xs]:good&=np.isfinite(f[c].to_numpy(float))
 q=f.loc[good].reset_index(drop=True);del f;release();print('PAIR_FRAME',v,controls,len(q),q.memory_usage(deep=True).sum(),flush=True);m=fit(q,xs);print('PAIR_FIT',v,controls,flush=True);Y2=legacy.demean(q[b].to_numpy(float).reshape(-1,1),m['e'],m['t'])[0][:,0];xty=np.zeros(len(m['names']))
 for j,pos in enumerate(m['indices']):xty[j]=np.asarray(m['a'][pos])@Y2
 bet2=m['bread']@xty;u2=Y2.copy()
 for start in range(0,len(q),32768):z=np.array(m['a'][m['indices'],start:start+32768]);u2[start:start+z.shape[1]]-=bet2@z
 j=m['names'].index('closed_x');xp=np.zeros(len(q))
 for k,pos in enumerate(m['indices']):xp+=m['bread'][j,k]*np.asarray(m['a'][pos])
 score=np.column_stack([xp*m['u'],xp*u2]);ns=len(m['ss']);nt=len(m['dd']);S=np.column_stack([np.bincount(m['stock'],weights=score[:,k],minlength=ns)for k in range(2)]);D=np.column_stack([np.bincount(m['date'],weights=score[:,k],minlength=nt)for k in range(2)]);V=(S.T@S*ns/(ns-1)+D.T@D*nt/(nt-1)-score.T@score*len(q)/(len(q)-1))*m['corr'];bet0=m['b'][j];betlag=bet2[j];total=bet0+betlag;se=np.sqrt(np.array([1,1])@V@np.array([1,1]));crit=student_t.ppf(.975,m['df']);rat,status,lo,hi=fieller(betlag,-bet0,V[1,1],V[0,0],-V[0,1],m['df']);net,ns0,nlo,nhi=fieller(total,-bet0,V.sum(),V[0,0],-V[0].sum(),m['df']);row=dict(variant=v,specification='full_control'if controls else'baseline',beta0_x100=bet0*100,lag_x100=betlag*100,total_x100=total*100,total_se_x100=se*100,total_ci_low_x100=(total-crit*se)*100,total_ci_high_x100=(total+crit*se)*100,recovery_ratio=rat,fieller_type=status,fieller_low=lo,fieller_high=hi,net_ratio=net,net_fieller_type=ns0,net_fieller_low=nlo,net_fieller_high=nhi,cov_beta0_lag=V[0,1],n=len(q),stocks=ns,events=q.event_id.nunique(),dates=nt,df=m['df']);assert abs(m['V'][j,j]-V[0,0])<1e-9;close(m)
 q['y']=q[a]+q[b];totalrow=run(q,xs,plan=plan('main'));row.update(total_p=totalrow.get('p'),total_wild_p=totalrow.get('wild_p'),total_ri_p=totalrow.get('ri_p'));assert abs(totalrow['beta']-total)<1e-8;return row

def table4():
 rows=[]
 for metric in ['if_delay','ih_delay']:
  f=read(['code','date','event_id','closed','dose',metric+'__w01']).rename(columns={metric+'__w01':'y'});eg=pd.read_csv(P/'R5/tables/F_event_classification.csv').set_index('event_id');f['hk']=f.event_id.map(eg.hkonly);f['closed_x']=f.closed*f.dose;f['hk_dose']=f.hk*f.dose;f['diff_x']=f.closed*f.hk_dose;rows.append(dict(metric=metric,specification='pooled_common_stock_FE_difference',**run(f,['closed_x','diff_x','dose','hk_dose'],term='diff_x',plan=plan('main'),dosecol='hk_dose')))
  # Fully separate stock FE by group equals the two subsample regressions,
  # because dates have unique ownership in the original mapping.
  f['entity']=f.code.astype(str)+'_'+f.hk.astype(str);rows.append(dict(metric=metric,specification='group_stock_FE_difference',**run(f,['closed_x','diff_x','dose','hk_dose'],term='diff_x',plan=None,entity='entity')))
 save(rows,'table4_difference_decomposition.csv')
def pair_task(job):return pair(*job)
if __name__=='__main__':
 import concurrent.futures as cf,multiprocessing as mp
 lock=json.loads((R/'meta/preregistration_lock.json').read_text());lock['estimation_started']=True;lock.setdefault('first_estimation_utc',pd.Timestamp.now(tz='UTC').isoformat());js(R/'meta/preregistration_lock.json',lock)
 dest=R/'tables/recovery_fieller.csv';out=pd.read_csv(dest).to_dict('records')if dest.exists()else[]
 for v in VARIANTS:
  for c in [False,True]:
   label='full_control'if c else'baseline'
   if any(x['variant']==v and x['specification']==label for x in out):continue
   with cf.ProcessPoolExecutor(max_workers=4,mp_context=mp.get_context('spawn'))as pool:out.append(list(pool.map(pair_task,[(v,c)]))[0])
   save(out,'recovery_fieller.csv');print('FIELLER',v,label,out[-1]['recovery_ratio'],flush=True);release()
 table4()
