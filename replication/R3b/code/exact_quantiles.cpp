#include <algorithm>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <vector>
int main(int argc,char**argv){
 if(argc!=3)return 2;std::ifstream in(argv[1],std::ios::binary);uint64_t n,F;in.read((char*)&n,8);in.read((char*)&F,8);std::vector<int32_t> dates(n),fr(F),order(n),rank(n),bit(n+1,0);std::vector<double> v(n),sorted(n);in.read((char*)dates.data(),n*4);in.read((char*)v.data(),n*8);in.read((char*)fr.data(),F*4);if(!in)return 3;
 std::iota(order.begin(),order.end(),0);std::sort(order.begin(),order.end(),[&](int a,int b){return v[a]<v[b]||(v[a]==v[b]&&a<b);});for(uint64_t j=0;j<n;j++){sorted[j]=v[order[j]];rank[order[j]]=j+1;}
 std::iota(order.begin(),order.end(),0);std::sort(order.begin(),order.end(),[&](int a,int b){return dates[a]<dates[b];});
 auto add=[&](int i){for(;i<=(int)n;i+=i&-i)bit[i]++;};auto kth=[&](int k){int pos=0;int step=1;while((step<<1)<=(int)n)step<<=1;for(;step;step>>=1){int q=pos+step;if(q<=(int)n&&bit[q]<k){pos=q;k-=bit[q];}}return pos;};
 std::ofstream out(argv[2]);out<<"freeze_day,n,q005,q01,q99,q995\n"<<std::setprecision(17);uint64_t count=0;
 for(int32_t freeze:fr){while(count<n&&dates[order[count]]<freeze){add(rank[order[count]]);count++;}out<<freeze<<","<<count;for(double q:{.005,.01,.99,.995}){double result=NAN;if(count){double h=(count-1)*q;int lo=(int)std::floor(h),hi=(int)std::ceil(h);double a=sorted[kth(lo+1)],b=sorted[kth(hi+1)],g=h-lo;result=g<.5?a+(b-a)*g:b-(b-a)*(1-g);}out<<","<<result;}out<<"\n";}
 return 0;
}
