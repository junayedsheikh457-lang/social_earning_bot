// FundedEdge market feed proxy helpers
const FE_REAL_SYMBOLS = new Set(['XAUUSD=X','EURUSD=X','JPYUSD=X','CHFUSD=X','GBPUSD=X','AUDUSD=X']);
const FE_OTC_BASE = {
  'BTCUSD-OTC':78194.36,
  'ETHUSD-OTC':3650.25,
  'XAUUSD-OTC':3650.10,
  'EURUSD-OTC':1.17120,
  'JPYUSD-OTC':0.00682,
  'CHFUSD-OTC':1.24850,
  'GBPUSD-OTC':1.35640,
  'AUDUSD-OTC':0.66310
};
const FE_OTC_STATE = {};
function feOtcPrice(symbol){
  const base=FE_OTC_BASE[symbol];
  if(!base)return null;
  const state=FE_OTC_STATE[symbol]||(FE_OTC_STATE[symbol]={price:base,time:Date.now()});
  const now=Date.now();
  const steps=Math.max(1,Math.floor((now-state.time)/1000));
  for(let i=0;i<steps;i++){
    const volatility=state.price>100?state.price*0.00018:state.price*0.00035;
    state.price=Math.max(state.price*0.0001,state.price+(Math.random()-0.5)*volatility);
  }
  state.time=now;
  return state.price;
}
module.exports={FE_REAL_SYMBOLS,feOtcPrice};
