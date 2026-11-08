// 282 exact_quantiles.cpp Fenwick/rank implementation, adapted to chronologically stored values and prefix counts.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>
int main(int argc,char**argv){
 if(argc!=4)return 2;std::ifstream in(argv[1],std::ios::binary|std::ios::ate);size_t n=in.tellg()/sizeof(double);in.seekg(0);std::vector<double> v(n),sorted(n);std::vector<int32_t> order(n),rank(n),bit(n+1,0);in.read((char*)v.data(),n*sizeof(double));if(!in)return 3;
 std::iota(order.begin(),order.end(),0);std::sort(order.begin(),order.end(),[&](int a,int b){return v[a]<v[b]||(v[a]==v[b]&&a<b);});for(size_t j=0;j<n;j++){sorted[j]=v[order[j]];rank[order[j]]=j+1;}
 auto add=[&](int i){for(;i<=(int)n;i+=i&-i)bit[i]++;};auto kth=[&](int k){int pos=0,step=1;while((step<<1)<=(int)n)step<<=1;for(;step;step>>=1){int q=pos+step;if(q<=(int)n&&bit[q]<k){pos=q;k-=bit[q];}}return pos;};
 std::ifstream req(argv[2]);std::ofstream out(argv[3]);std::string line;std::getline(req,line);out<<"event_id,freeze_day,n,stocks,q005,q01,q99,q995\n"<<std::setprecision(17);size_t count=0;
 while(std::getline(req,line)){std::replace(line.begin(),line.end(),',',' ');std::istringstream ss(line);long eid,freeze,nn,stocks;ss>>eid>>freeze>>nn>>stocks;if(nn<(long)count||nn>(long)n)return 4;while(count<(size_t)nn){add(rank[count]);count++;}out<<eid<<","<<freeze<<","<<count<<","<<stocks;for(double q:{.005,.01,.99,.995}){double result=NAN;if(count){double h=(count-1)*q;int lo=(int)std::floor(h),hi=(int)std::ceil(h);double a=sorted[kth(lo+1)],b=sorted[kth(hi+1)],g=h-lo;result=g<.5?a+(b-a)*g:b-(b-a)*(1-g);}out<<","<<result;}out<<"\n";}
 return 0;
}
