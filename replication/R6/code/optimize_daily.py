from pathlib import Path
p=Path('code/build_daily.py');s=p.read_text();s=s.replace('F={}','F={};SX={};RISK={};CURRENT_DAY=None\nimport warnings\nwarnings.filterwarnings("ignore",category=RuntimeWarning)')
a=s.index(' dd=pd.DataFrame(');b=s.index('\ndef one_day(',a)
s=s[:a]+''' dd=pd.DataFrame({'code':codes,'date':pd.Timestamp(day),'valid_minutes':n,'one_price':one,'amount':amount,'volume':np.nansum(vol[:,1:],1)})
 dd['age']=[np.searchsorted(ADATES,np.datetime64(day))-np.searchsorted(ADATES,np.datetime64(FIRST[c]))+1 for c in codes]
 dd['eligible_day']=(n>=180)&~one&(amount>0)&dd.age.ge(60)&~dd.code.isin(RISK)
 dd=pd.concat([dd,pd.DataFrame(bm.future_metrics(rr,np.full(len(rr),np.datetime64(day,'D').astype('int64'))))],axis=1)
 seg=None
 if segments:
  getfuture();dk=np.datetime64(day,'D').astype('int64');data={'code':np.tile(codes,8),'date':pd.Timestamp(day),'eligible_day':np.tile(dd.eligible_day.to_numpy(),8),'segment':np.repeat(np.arange(8),len(codes)),'segment_amount':np.nansum(amt[:,1:].reshape(len(codes),8,30),axis=2).T.ravel(),'valid_segment_returns':np.isfinite(rr.reshape(len(codes),8,30)).sum(2).T.ravel(),'regression_minutes':np.isfinite(rr.reshape(len(codes),8,30)[:,:,5:]).sum(2).T.ravel()}
  for p in ['IF','IH']:
   f=F[p].get(dk);ans=[]
   for j in range(8):
    key=(dk,p,j)
    if key not in SX:
     if f is None:SX[key]=None
     else:
      v=f[j*30:(j+1)*30];xx=np.column_stack([np.ones(30),v,*[np.r_[np.full(l,np.nan),v[:-l]] for l in range(1,6)]]);xx[:5]=np.nan;good=np.isfinite(xx).all(1);x=xx[good];SX[key]=(good,x,np.linalg.pinv(x),np.linalg.pinv(x[:,:2])) if len(x)>=20 and np.linalg.matrix_rank(x)==7 else None
    ds=SX[key];z=np.full(len(rr),np.nan)
    if ds is not None:
     good,x,A,A0=ds;y=rr[:,j*30:(j+1)*30][:,good];complete=np.isfinite(y).all(1);ids=np.flatnonzero(complete)
     if len(ids):
      v=y[ids];b=v@A.T;b0=v@A0.T;sst=((v-v.mean(1)[:,None])**2).sum(1)
      with np.errstate(divide='ignore',invalid='ignore'):
       r2=1-((v-b@x.T)**2).sum(1)/sst;r20=1-((v-b0@x[:,:2].T)**2).sum(1)/sst;z[ids]=np.where(r2>1e-10,1-r20/r2,np.nan)
     for i in np.flatnonzero(~complete):
      v=np.isfinite(y[i]);a=x[v];yy=y[i,v]
      if len(yy)<20 or np.linalg.matrix_rank(a)<7:continue
      ss=((yy-yy.mean())**2).sum()
      if ss<=0:continue
      r2=1-((yy-a@np.linalg.lstsq(a,yy,rcond=None)[0])**2).sum()/ss;r20=1-((yy-a[:,:2]@np.linalg.lstsq(a[:,:2],yy,rcond=None)[0])**2).sum()/ss
      if r2>1e-10:z[i]=1-r20/r2
    ans.append(z)
   data[p.lower()+'_delay']=np.concatenate(ans)
  seg=pd.DataFrame(data)
 return dd,seg
''' +s[b:]
s=s.replace("day=str(day);t=pd.Timestamp(day)","global SX,RISK\n SX={};day=str(day);t=pd.Timestamp(day);RISK=set(ST.loc[pd.to_datetime(ST.st_start).le(t)&pd.to_datetime(ST.st_end).fillna(pd.Timestamp('2100-01-01')).ge(t),'ts_code'])")
p.write_text(s)
