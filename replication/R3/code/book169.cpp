// Optional native implementation of rebuild_v2.replay_python. No Python state.
#include <cstdint>
#include <cmath>
#include <map>
#include <unordered_map>
#include <vector>
#include <algorithm>
using I=int64_t;
struct Order { int side; I price; double left; bool active; };
struct Book {
 std::map<I,double> bid,ask;
 std::map<I,std::vector<I>> pb,ps;
 std::unordered_map<I,Order> state;
 I *q; bool cage; I now,lastprice;
 Book(I *q_,bool c,I p):q(q_),cage(c),now(0),lastprice(p){}
 I best(int s) { auto &m=s==1?bid:ask; return m.empty()?0:(s==1?m.rbegin()->first:m.begin()->first); }
 void change(int s,I p,double v) { if(p<=0)return;auto &m=s==1?bid:ask;double x=m[p]+v;if(x<=0)m.erase(p);else m[p]=x; }
 double volume(int s,I p) { auto &m=s==1?bid:ask;auto i=m.find(p);return i==m.end()?0:i->second; }
 bool continuous(){return (now>=34200000&&now<41400000)||(now>=46800000&&now<53820000);}
 std::pair<I,I> bounds(){I b=best(1),a=best(-1);I x=a?a:(b?b:lastprice),y=b?b:(a?a:lastprice);return {(x*102+5000)/10000*100,(y*98+5000)/10000*100};}
 void reduce(I key,double vol,bool cancel,int expected){
  if(key<=0)return;q[0]++;auto it=state.find(key);if(it==state.end()){q[1]++;return;}
  auto &o=it->second;if(expected&&expected!=o.side)q[3]++;
  if(!o.active&&!cancel&&continuous())q[4]++;
  if(vol>o.left)q[2]++;double used=std::min(vol,o.left);if(o.active)change(o.side,o.price,-used);o.left-=used;
 }
 void activate(){
  if(!cage)return;
  if(now>=53820000){
   for(auto *m:{&pb,&ps})for(auto &v:*m)for(I k:v.second){auto &o=state[k];if(o.left>0&&!o.active){o.active=true;change(o.side,o.price,o.left);}}
   pb.clear();ps.clear();return;
  }
  I b=best(1),a=best(-1);if(b&&a&&b>=a)return;
  bool changed=true;
  while(changed){
   changed=false;auto range=bounds();
   while(!pb.empty()){
    auto it=pb.begin();I p=it->first;
    // Discard exhausted records even if their price is not yet admissible.
    auto &vv=it->second;vv.erase(std::remove_if(vv.begin(),vv.end(),[&](I k){auto &o=state[k];return o.left<=0||o.active;}),vv.end());
    if(vv.empty()){pb.erase(it);continue;}if(p>range.first)break;
    for(I k:vv){auto &o=state[k];o.active=true;change(o.side,p,o.left);q[12]++;changed=true;}pb.erase(it);
   }
   while(!ps.empty()){
    auto it=std::prev(ps.end());I p=it->first;auto &vv=it->second;
    vv.erase(std::remove_if(vv.begin(),vv.end(),[&](I k){auto &o=state[k];return o.left<=0||o.active;}),vv.end());
    if(vv.empty()){ps.erase(it);continue;}if(p<range.second)break;
    for(I k:vv){auto &o=state[k];o.active=true;change(o.side,p,o.left);q[12]++;changed=true;}ps.erase(it);
   }
   b=best(1);a=best(-1);if(b&&a&&b>=a)break;
  }
 }
};
extern "C" I replay169(I n,I nt,const I *ix,const I *tm,const I *oi,const I *side,const I *price,const double *qty,const int8_t *typ,const I *bi,const I *ai,const double *tq,const I *tp,const int8_t *cancel,int sh,int cage,I prevclose,I *counts,I *outtime,I *outbid,I *outask,double *outvb,double *outva){
 try {
  Book b(counts,cage,prevclose);b.state.reserve(n*13/10+10);I last=-1,used=0;
  auto record=[&](I t){I bp=b.best(1),ap=b.best(-1);outtime[used]=t;outbid[used]=bp;outask[used]=ap;outvb[used]=b.volume(1,bp);outva[used]=b.volume(-1,ap);used++;};
  for(I k=0;k<n+nt;k++){
   I e=ix[k],now=tm[e];if(now!=last){if(last>=0)record(last);last=now;}b.now=now;
   if(e<n){
    I key=oi[e],s=side[e],p=price[e];double vol=qty[e];int flag=typ[e];
    if(flag==3){if(vol<=0&&b.state.count(key))vol=b.state[key].left;b.reduce(key,vol,true,s);counts[5]++;continue;}
    if(key<=0||(s!=1&&s!=-1)||vol<=0){counts[6]++;continue;}
    auto it=b.state.find(key);if(it!=b.state.end()&&it->second.left>0){counts[7]++;continue;}
    if(flag==1){p=0;counts[8]++;}
    if(flag==2){p=b.best(s);counts[9]++;if(p<=0)counts[10]++;}
    bool deferred=false;
    if(cage&&b.continuous()&&flag==0&&p>0){auto range=b.bounds();deferred=s==1?p>range.first:p<range.second;}
    b.state[key]={(int)s,p,vol,!deferred};
    if(deferred){(s==1?b.pb:b.ps)[p].push_back(key);counts[11]++;}else if(p>0)b.change(s,p,vol);
   } else {
    I j=e-n;I buy=bi[j],sell=ai[j];bool c=cancel[j];if(!c)b.lastprice=tp[j];
    if(sh&&b.continuous()&&!c){counts[13]++;if(buy>sell)b.reduce(sell,tq[j],false,-1);else b.reduce(buy,tq[j],false,1);}
    else {b.reduce(buy,tq[j],c,1);b.reduce(sell,tq[j],c,-1);}
   }
   if(cage)b.activate();
  }
  if(last>=0)record(last);return used;
 }catch(...){return -1;}
}
