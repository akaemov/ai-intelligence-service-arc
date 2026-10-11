import {test} from 'node:test';
import assert from 'node:assert/strict';
import ts from 'typescript';
import {readFileSync} from 'node:fs';
const code=ts.transpileModule(readFileSync(new URL('../src/utils.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
const {filterObservations,safeUrl,csvExport}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const rows=[{title:'Нужен маркетолог',short_evidence_excerpt:'Вакансия',source_name:'HH',signal_type:'C',service_category:'marketing',city_or_district:'Уфа',customer_segment:'business'},{title:'Предлагаем рекламу',short_evidence_excerpt:'Предложение',source_name:'Компания',signal_type:'D',service_category:'advertising',city_or_district:'Салават',customer_segment:null}];
const empty={query:'',signal:'',service:'',city:'',segment:''};
test('filters combine geography, signal, segment and text',()=>{assert.equal(filterObservations(rows,{...empty,query:'МАРКЕТОЛОГ',signal:'C',city:'Уфа',segment:'business'}).length,1);assert.equal(filterObservations(rows,{...empty,signal:'A'}).length,0);assert.equal(filterObservations(rows,{...empty,segment:'unknown'}).length,1)});
test('links reject script and embedded credentials',()=>{assert.equal(safeUrl('javascript:alert(1)'),'#');assert.equal(safeUrl('https://user:pass@example.org'),'#');assert.equal(safeUrl('https://example.org/x'),'https://example.org/x')});
test('CSV prevents spreadsheet formula execution',()=>assert.ok(csvExport([{title:'=HYPERLINK("bad")'}]).includes("'=HYPERLINK")));

test('customer geography differs from execution and target market',()=>{
 const record={...rows[0],country:'Россия',customer_region:'Республика Башкортостан',customer_city:'Уфа',execution_geography:'Москва',target_market_geography:'Россия',federal_eligible:true,regional_eligible:true};
 assert.equal(filterObservations([record],{...empty,region:'Москва'}).length,0);
 assert.equal(filterObservations([record],{...empty,region:'Республика Башкортостан',scope:'regional'}).length,1);
});
test('period, unknown geography and government remain separate',()=>{
 const record={...rows[0],published_at:'2026-10-10T00:00:00+00:00',customer_segment:'government',federal_eligible:false,confidence_level:'low'};
 assert.equal(filterObservations([record],{...empty,segment:'government',from:'2026-10-09',to:'2026-10-11',scope:'unknown',source:'HH',confidence:'low'}).length,1);
 assert.equal(filterObservations([record],{...empty,scope:'federal'}).length,0);
 assert.equal(filterObservations([{...record,published_at:null}],{...empty,from:'2026-10-01'}).length,0);
});
test('budget ranges preserve endpoints and do not invent averages',()=>{
 const record={...rows[0],explicit_budget:null,budget_min:300000,budget_max:900000,currency:'RUB'};
 assert.equal(filterObservations([record],{...empty,budgetMin:'200000',budgetMax:'1000000',currency:'RUB'}).length,1);
 assert.equal(filterObservations([record],{...empty,budgetMin:'600000'}).length,0);
 assert.equal(filterObservations([record],{...empty,currency:'USD'}).length,0);
 assert.ok(csvExport([record]).includes('"300000","900000"'));
});
