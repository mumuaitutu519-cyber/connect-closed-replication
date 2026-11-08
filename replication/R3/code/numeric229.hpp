#pragma once
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cctype>
#include <limits>
#include <stdexcept>
#include <string>

inline long long numeric229(const std::string& s) {
 if(s.empty()||s=="NaN"||s=="nan"||s=="NULL"||s=="null") return 0;
 const char* begin=s.c_str();char* end=nullptr;errno=0;
 long long integer=std::strtoll(begin,&end,10);
 while(end&&std::isspace(static_cast<unsigned char>(*end)))++end;
 if(end!=begin&&end&&*end=='\0'&&errno!=ERANGE)return integer;
 // Parse decimal/exponent notation as exact decimal digits, including IDs above
 // 2^53. Apple arm64 long double is not a wider integer-safe alternative.
 std::string token=s;while(!token.empty()&&std::isspace(static_cast<unsigned char>(token.back())))token.pop_back();size_t left=0;while(left<token.size()&&std::isspace(static_cast<unsigned char>(token[left])))++left;token.erase(0,left);
 if(token.empty()||token=="NaN"||token=="nan"||token=="NULL"||token=="null")return 0;
 size_t pos=0;bool negative=false;if(token[pos]=='+'||token[pos]=='-'){negative=token[pos]=='-';++pos;}
 std::string digits;bool dot=false;int fractional=0;
 while(pos<token.size()&&token[pos]!='e'&&token[pos]!='E'){
  char c=token[pos++];if(c>='0'&&c<='9'){digits.push_back(c);fractional+=dot;}else if(c=='.'&&!dot)dot=true;else throw std::runtime_error("invalid numeric token: "+s);
 }
 if(digits.empty())throw std::runtime_error("numeric token has no digits: "+s);
 long exponent=0;if(pos<token.size()){
  ++pos;const char* ebegin=token.c_str()+pos;errno=0;exponent=std::strtol(ebegin,&end,10);
  if(end==ebegin||*end!='\0'||errno==ERANGE||exponent>10000||exponent<-10000)throw std::runtime_error("invalid numeric exponent: "+s);
 }
 size_t first=digits.find_first_not_of('0');if(first==std::string::npos)return 0;digits.erase(0,first);long places=exponent-fractional;
 if(places<0){size_t remove=static_cast<size_t>(-places);if(remove>digits.size()||digits.find_first_not_of('0',digits.size()-remove)!=std::string::npos)throw std::runtime_error("nonintegral raw integer: "+s);digits.resize(digits.size()-remove);}
 else {if(digits.size()+static_cast<size_t>(places)>19)throw std::runtime_error("out-of-range raw integer: "+s);digits.append(static_cast<size_t>(places),'0');}
 if(digits.size()>19)throw std::runtime_error("out-of-range raw integer: "+s);
 unsigned __int128 magnitude=0;for(char c:digits)magnitude=magnitude*10+(c-'0');unsigned __int128 bound=static_cast<unsigned long long>(std::numeric_limits<long long>::max());
 if(magnitude>bound+(negative?1:0))throw std::runtime_error("out-of-range raw integer: "+s);
 if(negative&&magnitude==bound+1)return std::numeric_limits<long long>::min();
 return negative?-static_cast<long long>(magnitude):static_cast<long long>(magnitude);
}
inline long long numeric229_field(const char* begin,const char* end) {
 const char* stop=begin;while(stop<end&&*stop!=',')++stop;
 return numeric229(std::string(begin,stop-begin));
}
