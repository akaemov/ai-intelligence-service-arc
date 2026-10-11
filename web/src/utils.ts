export interface Observation {
 observation_id:string;source_url:string;source_name:string;title:string;short_evidence_excerpt:string;signal_type:string;
 service_category:string|null;customer_segment:string|null;published_at:string|null;collected_at:string;
 region:string|null;city_or_district:string|null;country:string|null;customer_region:string|null;customer_city:string|null;
 federal_district:string|null;execution_geography:string|null;target_market_geography:string|null;contractor_search_geography:string|null;
 remote_delivery:boolean|null;geography_evidence:string|null;confidence_level:string;confidence_reason:string;
 factual_summary:string;analyst_interpretation:string|null;explicit_budget:number|null;budget_min?:number|null;budget_max?:number|null;currency:string|null;budget_basis:string|null;price_type:string|null;
 limitations:string[];regional_eligible:boolean;federal_eligible:boolean;industry:string|null;organization_name:string|null;
 organization_size:string|null;customer_problem:string|null;requested_service:string|null;requirements:string|null;
}
export interface Filters {query:string;signal:string;service:string;city:string;segment:string;region?:string;district?:string;industry?:string;source?:string;confidence?:string;from?:string;to?:string;budgetMin?:string;budgetMax?:string;currency?:string;scope?:string}
const match=(value:string|null|undefined,filter:string|undefined)=>!filter||(filter==='__unknown__'?!value:value===filter);
export function filterObservations(rows:Observation[],f:Filters):Observation[]{return rows.filter(o=>{
 const lower=o.explicit_budget??o.budget_min;const upper=o.explicit_budget??o.budget_max;
 if(f.budgetMin&&(lower==null||!Number.isFinite(Number(f.budgetMin))||lower<Number(f.budgetMin)))return false;
 if(f.budgetMax&&(upper==null||!Number.isFinite(Number(f.budgetMax))||upper>Number(f.budgetMax)))return false;
 if(f.from&&(!o.published_at||o.published_at.slice(0,10)<f.from))return false;
 if(f.to&&(!o.published_at||o.published_at.slice(0,10)>f.to))return false;
 if(f.scope==='federal'&&!o.federal_eligible)return false;
 if(f.scope==='regional'&&!o.regional_eligible)return false;
 if(f.scope==='unknown'&&o.federal_eligible)return false;
 return (!f.query||[o.title,o.short_evidence_excerpt,o.source_name,o.customer_problem].join(' ').toLocaleLowerCase('ru').includes(f.query.toLocaleLowerCase('ru')))
 &&match(o.signal_type,f.signal)&&match(o.service_category,f.service)&&match(o.customer_city??o.city_or_district,f.city)
 &&match(o.customer_segment??'unknown',f.segment)&&match(o.customer_region??o.region,f.region)
 &&match(o.federal_district,f.district)&&match(o.industry,f.industry)&&match(o.source_name,f.source)
 &&match(o.confidence_level,f.confidence)&&match(o.currency,f.currency);
 });}
export function safeUrl(value:string):string{try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:'#';}catch{return '#';}}
export function csvExport(rows:Observation[]):string{
 const keys:(keyof Observation)[]=['observation_id','source_name','source_url','title','signal_type','service_category','customer_segment','industry','published_at','country','federal_district','customer_region','customer_city','execution_geography','target_market_geography','contractor_search_geography','remote_delivery','short_evidence_excerpt','explicit_budget','budget_min','budget_max','currency','budget_basis','price_type','confidence_level'];
 const cell=(v:unknown)=>{let s=v==null?'':String(v);if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
 return '\uFEFF'+[keys.map(cell).join(','),...rows.map(o=>keys.map(k=>cell(o[k])).join(','))].join('\r\n');
}
