from common import *
import inference as inf

def main():
 rng=np.random.default_rng(74);ns=40;nt=12;seg=4;c=np.repeat(np.arange(ns),nt*seg);day=np.tile(np.repeat(np.arange(nt),seg),ns);s=np.tile(np.arange(seg),ns*nt);dose=rng.normal(size=ns)[c];x=(day%3==0)*(s<2)*dose;y=.17*x+rng.normal(size=len(c))*.2+rng.normal(size=ns*nt)[c*nt+day]+s*.03;d=pd.DataFrame(dict(code=c,date=day,event_id=101,stock_day=c*nt+day,segment=s,x=x,y=y));m,status=inf.fit(d,'y',['x'],'stock_day','segment');x0=d.x-d.groupby('stock_day').x.transform('mean')-d.groupby('segment').x.transform('mean')+d.x.mean();y0=d.y-d.groupby('stock_day').y.transform('mean')-d.groupby('segment').y.transform('mean')+d.y.mean();beta=(x0@y0)/(x0@x0);u=y0-beta*x0;score=x0*u;q=pd.DataFrame(dict(s=score,c=c,t=day));S=q.groupby('c').s.sum();D=q.groupby('t').s.sum();C=q.groupby(['c','t']).s.sum();N=len(d);var=(S@S*ns/(ns-1)+D@D*nt/(nt-1)-C@C*len(C)/(len(C)-1))/(x0@x0)**2*(N-1)/(N-ns*nt-seg)
 assert abs(beta-m['b'][0])<1e-10 and abs(var-m['V'][0,0])<1e-10
 (R/'logs/independent_cgm_check.json').write_text(json.dumps(dict(status='PASS',beta_error=float(abs(beta-m['b'][0])),variance_error=float(abs(var-m['V'][0,0])),stock_clusters=ns,date_clusters=nt,intersection_clusters=len(C)),indent=2))
 mapping=pd.read_csv(R/'tables/event_map.csv',parse_dates=['date']);out=[]
 for family in ['weather','partial','placebo']:
  z=mapping[mapping.family.eq(family)].copy();z['code']='design_only';dates,Z,a,meta=inf.calendar_plan(z,family,1000);out.append(meta);a['count_scope']='calendar design only, no stock observations';a['calendar_rows']=a['n'];a['n']=0;a['stocks']=0;a['stock_clusters']=0;a.to_csv(R/'tables'/('design_support_'+family+'.csv'),index=False)
 (R/'meta/pre_estimation_ri_support.json').write_text(json.dumps(out,indent=2));print('Independent FWL and stock/date intersection CGM checks passed')
if __name__=='__main__':main()
