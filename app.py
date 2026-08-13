
import json
from pathlib import Path

import requests, pandas as pd, numpy as np, streamlit as st
st.set_page_config(page_title="داشبورد سرمایه دانا V10",page_icon="🪙",layout="wide")
H={"User-Agent":"Mozilla/5.0"}

@st.cache_data(ttl=300)
def snapshot():
    try:
        return json.loads((Path(__file__).parent / "data" / "market_snapshot.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

def saved(sym):
    return snapshot().get("symbols",{}).get(sym,{})

@st.cache_data(ttl=30)
def search(s):
    try:
        r=requests.get(f"https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{requests.utils.quote(s)}",headers=H,timeout=10);r.raise_for_status()
        d=r.json();x=d.get("instrumentSearch",d)
        if isinstance(x,dict):x=x.get("instrumentSearch",x.get("items",[]))
        return x if isinstance(x,list) else []
    except requests.RequestException:
        return []
def find(s):
    a=search(s)
    for z in a:
        if str(z.get("lVal18AFC",z.get("symbol","")))==s:return z
    return a[0] if a else None
@st.cache_data(ttl=15)
def hist(i):
    try:
        r=requests.get(f"https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{i}/365",headers=H,timeout=10);r.raise_for_status()
        d=r.json();x=d.get("closingPriceDaily",d)
        if isinstance(x,dict):x=x.get("closingPriceDaily",x.get("items",[]))
        rows=[{"date":z.get("dEven"),"close":z.get("pClosing") or z.get("pc"),"volume":z.get("qTotTran5J") or 0} for z in (x if isinstance(x,list) else [])]
    except requests.RequestException:
        return pd.DataFrame()
    df=pd.DataFrame(rows)
    if df.empty:return df
    for c in ["close","volume"]:df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
@st.cache_data(ttl=20)
def client(i):
    try:
        r=requests.get(f"https://cdn.tsetmc.com/api/ClientType/GetClientType/{i}/1/0",headers=H,timeout=10);r.raise_for_status()
        d=r.json();return d.get("clientType",d)
    except:return None
def num(d,*ks):
    if not isinstance(d,dict):return None
    for k in ks:
        try:
            if d.get(k) is not None:return float(d[k])
        except:pass
    return None
def tech(df):
    x=df.copy();x["EMA20"]=x.close.ewm(span=20,adjust=False).mean();x["EMA50"]=x.close.ewm(span=50,adjust=False).mean();x["EMA200"]=x.close.ewm(span=200,adjust=False).mean()
    d=x.close.diff();g=d.clip(lower=0).ewm(alpha=1/14,adjust=False).mean();l=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False).mean();x["RSI"]=100-100/(1+g/l.replace(0,pd.NA))
    e12=x.close.ewm(span=12,adjust=False).mean();e26=x.close.ewm(span=26,adjust=False).mean();x["MACD"]=e12-e26;x["Signal"]=x.MACD.ewm(span=9,adjust=False).mean()
    return x
def analyze(sym):
    cached=saved(sym)
    h=find(sym);i=h.get("insCode") if h else cached.get("insCode")
    if not i:return None
    df=hist(i)
    used_snapshot=False
    if df.empty and cached.get("history"):
        df=pd.DataFrame(cached["history"])
        for c in ["close","volume"]:df[c]=pd.to_numeric(df[c],errors="coerce")
        df=df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
        used_snapshot=True
    if df.empty or len(df)<6:return None
    t=tech(df);z=t.iloc[-1];s=0;why=[]
    for ok,w,msg in [(z.close>z.EMA20,15,"قیمت بالای EMA20"),(z.EMA20>z.EMA50,15,"EMA20 بالای EMA50"),(z.EMA50>z.EMA200,15,"روند بلندمدت مثبت"),(z.RSI>=50,10,"RSI مثبت"),(z.MACD>z.Signal,15,"MACD مثبت")]:
        if ok:s+=w;why.append(msg)
    av=t.volume.tail(20).mean()
    if av and t.volume.iloc[-1]>1.2*av:s+=10;why.append("حجم بالاتر از میانگین")
    ct=client(i)
    if not isinstance(ct,dict):ct=cached.get("client")
    if isinstance(ct,dict):
        bi=num(ct,"buy_I_Volume");si=num(ct,"sell_I_Volume")
        if bi is not None and si is not None:
            if bi>1.15*si:s+=20;why.append("خرید حقیقی قوی")
            elif si>1.15*bi:s-=10;why.append("فشار فروش حقیقی")
    cur=float(z.close)
    sup=sorted([x for x in [float(df.close.tail(20).min()),float(df.close.tail(60).min())] if x<cur],reverse=True)
    res=sorted([x for x in [float(df.close.tail(20).max()),float(df.close.tail(60).max())] if x>cur])
    s1=sup[0] if sup else float(df.close.tail(20).min());r1=res[0] if res else float(df.close.tail(20).max())
    stop=s1*.985;entry_low=max(s1,cur*.985);entry_high=min(cur*1.005,r1*.995)
    if entry_low>=entry_high:entry_low=min(cur,s1);entry_high=max(cur,min(r1,cur*1.01))
    rr=(r1-cur)/(cur-stop) if cur>stop else np.nan
    ret=t.close.pct_change().dropna();daily=float(np.clip(.45*(z.EMA20/z.EMA50-1)/5+.35*(z.EMA50/z.EMA200-1)/10+.2*(z.close/t.close.iloc[-6]-1)/5,-.004,.004))
    exp=(1+daily)**30-1
    return {"sym":sym,"score":max(0,min(100,s)),"why":why,"cur":cur,"support":s1,"resistance":r1,"entry":(entry_low,entry_high),"stop":stop,"rr":rr,"exp30":exp,"t":t,"snapshot":used_snapshot}

def toman(x):return f"{x/10:,.0f}"
capital=st.sidebar.number_input("سرمایه (تومان)",min_value=0.0,value=2300000000.0,step=10000000.0)
afran=st.sidebar.number_input("بازده سالانه افران (%)",min_value=0.0,max_value=100.0,value=30.0,step=.1)
switch=st.sidebar.number_input("هزینه جابه‌جایی کل (%)",min_value=0.0,max_value=10.0,value=.2,step=.05)
horizon=st.sidebar.selectbox("افق تصمیم",[7,14,30],index=2)

zar=analyze("زر");fzr=analyze("فزر")
items=[x for x in [zar,fzr] if x]
for x in items:
    x["afran_gain"]=capital*afran/100*horizon/365
    x["net_adv"]=capital*x["exp30"]/100*0 if False else capital*x["exp30"]-capital*switch/100-x["afran_gain"]

st.title("🪙 داشبورد سرمایه دانا — نسخه ۱۰")
st.caption("یک صفحه برای تصمیم روزانه سرمایه")

if not items:
    st.error("دادهٔ زندهٔ TSETMC از سرورهای Streamlit Cloud قابل دریافت نیست. برای نسخهٔ عمومی باید یک API دادهٔ جایگزین یا پراکسی سرور داخل ایران متصل شود.")
else:
    if any(x["snapshot"] for x in items):
        stamp=snapshot().get("generated_at","نامشخص")
        st.info(f"دادهٔ زندهٔ TSETMC در دسترس نبود؛ آخرین دادهٔ ذخیره‌شده ({stamp}) نمایش داده می‌شود.")
    best=max(items,key=lambda x:(x["net_adv"],x["score"]))
    # conservative final decision
    if best["score"]>=75 and np.isfinite(best["rr"]) and best["rr"]>=1.5 and best["net_adv"]>0 and best["exp30"]>0:
        final="🟢 ورود پله‌ای به "+best["sym"]
    elif best["score"]>=60 and np.isfinite(best["rr"]) and best["rr"]>=1.2:
        final="🟡 صبر / ورود مشروط به "+best["sym"]
    else:
        final="🔴 فعلاً در افران بمان"
    st.success(f"## تصمیم امروز: {final}")
    a,b,c,d=st.columns(4)
    a.metric("سرمایه",f"{capital:,.0f} تومان")
    b.metric("افق",f"{horizon} روز")
    b.caption(f"بازده افران سالانه: {afran:.1f}%")
    c.metric("هزینه جابه‌جایی",f"{capital*switch/100:,.0f} تومان")
    d.metric("بهترین گزینه",best["sym"])

    st.subheader("📌 خلاصه تصمیم")
    st.write(f"**امتیاز {best['sym']}:** {best['score']}/100")
    st.write(f"**سناریوی ۳۰ روزه:** {best['exp30']*100:+.2f}%")
    st.write(f"**مزیت خالص نسبت به افران:** {best['net_adv']:,.0f} تومان")
    st.write(f"**محدوده ورود:** {toman(best['entry'][0])} تا {toman(best['entry'][1])} تومان")
    st.write(f"**حد ضرر:** {toman(best['stop'])} تومان")
    st.write(f"**مقاومت/هدف اول:** {toman(best['resistance'])} تومان")
    st.write(f"**R/R:** {best['rr']:.2f}" if np.isfinite(best["rr"]) else "**R/R:** قابل محاسبه نیست")
    st.write("**چرا؟** "+"، ".join(best["why"]) if best["why"] else "تأیید کافی وجود ندارد.")

    st.divider()
    st.subheader("🔄 مقایسه زر و فزر")
    rows=[]
    for x in sorted(items,key=lambda x:x["net_adv"],reverse=True):
        rows.append({"نماد":x["sym"],"امتیاز":x["score"],"سناریوی ۳۰ روزه":f"{x['exp30']*100:+.2f}%","مزیت نسبت به افران":f"{x['net_adv']:,.0f} تومان","R/R":f"{x['rr']:.2f}" if np.isfinite(x["rr"]) else "—"})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)

    st.divider()
    st.subheader("📊 جزئیات زر و فزر")
    tabs=st.tabs([x["sym"] for x in items])
    for tab,x in zip(tabs,items):
        with tab:
            st.write(f"**حمایت:** {toman(x['support'])} تومان | **مقاومت:** {toman(x['resistance'])} تومان")
            st.write(f"**ورود:** {toman(x['entry'][0])} تا {toman(x['entry'][1])} تومان | **حد ضرر:** {toman(x['stop'])} تومان")
            st.line_chart(x["t"].set_index("date")[["close","EMA20","EMA50","EMA200"]].tail(120))

    st.divider()
    st.subheader("⚙️ راهنمای استفاده روزانه")
    st.write("""
1. برنامه را باز کن و فقط سرمایه، بازده افران و هزینه جابه‌جایی را در صورت تغییر اصلاح کن.
2. ابتدا «تصمیم امروز» را ببین.
3. اگر 🟢 بود، محدوده ورود و حد ضرر را بررسی کن و ورود را **پله‌ای** انجام بده.
4. اگر 🟡 بود، صبر کن تا شرط‌های برنامه بهتر شوند.
5. اگر 🔴 بود، برنامه فعلاً افران را ترجیح می‌دهد.
6. قبل از معامله واقعی، خبرهای مهم دلار و انس و شرایط لحظه‌ای بازار را هم بررسی کن.
""")
st.warning("این برنامه تصمیم‌یار است، نه تضمین سود. داده‌های عمومی ممکن است ناقص/قطع شوند و سناریوهای آینده قطعی نیستند.")
