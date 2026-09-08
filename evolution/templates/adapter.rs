// Reconstructed demonstration binding, not a historical production release.
use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{json, Map, Value};
use std::{collections::BTreeSet, fmt, io::{self, BufRead}};
mod profile;
use profile::LEVEL;
type Result<T> = std::result::Result<T, &'static str>;
const ROOTS: &[&[&str]] = &[
    &["tableId","tableName","title","stringValues","numericValues"],
    &["columns","rows","styleMatrix"],
    &["sparseOverride","sparseOverrideTypes"],
    &["stylebook","fontConfig"],
    &["imageManager","cellBackgroundImageRefs","cellIds","dataBarScale","cellDataBars","captureTokens"],
    &["columnPriority","rowPriority","hiddenColumns","hiddenRows"],
];
fn require(ok:bool, code:&'static str)->Result<()> {if ok {Ok(())} else {Err(code)}}
fn integer(v:Option<&Value>, code:&'static str)->Result<i32> {
    let d=v.and_then(Value::as_f64).ok_or(code)?;
    require(d.is_finite() && d.fract()==0.0 && d>=i32::MIN as f64 && d<=i32::MAX as f64,code)?; Ok(d as i32)
}
fn pointer(s:&str)->String {s.replace('~',"~0").replace('/',"~1")}
fn project(obj:&mut Map<String,Value>,fields:&BTreeSet<&str>,extra:bool,path:&str,lost:&mut Vec<String>) {
    let keys:Vec<_>=obj.iter().filter(|(k,v)|(!fields.contains(k.as_str()) && !extra)||(fields.contains(k.as_str()) && v.is_null())).map(|(k,_)|k.clone()).collect();
    for k in keys {obj.remove(&k);lost.push(format!("{path}/{}",pointer(&k)));}
}
fn metadata(table:&mut Map<String,Value>,name:&str,column:bool,lost:&mut Vec<String>)->Result<()> {
    if let Some(node)=table.get_mut(name) {
        let rows=node.as_array_mut().ok_or("metadata")?;
        let mut fields:BTreeSet<&str>=if column {vec!["id","header","typeHint","width","alignment"]}else{vec!["id","header","height"]}.into_iter().collect();
        if LEVEL==5 {fields.insert(if column {"widthExpr"}else{"heightExpr"});fields.insert("hidden");}
        for (i,item) in rows.iter_mut().enumerate() {
            let row=item.as_object_mut().ok_or("metadata")?;project(row,&fields,LEVEL==5,&format!("/{name}/{i}"),lost);
            for k in &fields {if let Some(v)=row.get(*k) {
                if *k=="hidden" {require(v.is_boolean(),"metadata")?;}
                else if k.ends_with("Expr") {require(v.is_object(),"expression")?;}
                else {require(v.is_string(),"metadata")?;}
            }}
        }
    } Ok(())
}
fn process(mut node:Value)->Result<Value> {
    let table=node.as_object_mut().ok_or("table")?;let mut lost=vec![];
    if LEVEL>=3 {require(!["allStylesLight","allStylesDark","allStylesExtra","themes"].iter().any(|k|table.contains_key(*k)),"forbidden-key")?;}
    let fields:BTreeSet<&str>=ROOTS.iter().take(LEVEL+1).flat_map(|x|x.iter().copied()).collect();
    project(table,&fields,LEVEL>=3,"",&mut lost);
    for k in ["tableId","tableName","title"] {if let Some(v)=table.get(k) {require(v.is_string(),"identity")?;}}
    let mut shape=None;
    for k in ["stringValues","numericValues","styleMatrix"] {if fields.contains(k) {if let Some(grid)=table.get(k) {
        let rows=grid.as_array().ok_or("grid-shape")?;let mut cols=None;
        for row in rows {let cells=row.as_array().ok_or("grid-shape")?;
            require(cols.is_none() || cols==Some(cells.len()),"grid-shape")?;cols=Some(cells.len());
            for v in cells {require(v.is_null() || if k=="numericValues" {v.as_f64().is_some_and(f64::is_finite)}else{v.is_string()},"cell-type")?;}
        }
        let now=(rows.len(),cols.unwrap_or(0));require(shape.is_none() || shape==Some(now),"grid-shape")?;shape=Some(now);
    }}}
    if LEVEL>=1 {metadata(table,"columns",true,&mut lost)?;metadata(table,"rows",false,&mut lost)?;}
    if LEVEL>=2 {if let Some(sparse)=table.get_mut("sparseOverride") {
        let groups=sparse.as_object_mut().ok_or("sparse")?;let mut occupied=BTreeSet::new();
        let mut cell_fields:BTreeSet<&str>=["rowIndex","colIndex","rowSpan","colSpan","value","valueNumeric","styleKey","typeRef","formula","formatString"].into_iter().collect();
        if LEVEL>=4 {cell_fields.extend(["imageRef","imageAlt","imageFit","imageZoomable","videoRef","posterRef","videoControls","videoMuted","videoLoop","videoFit","mathTex","mathAst"]);}
        for (key,items) in groups {for(i,item)in items.as_array_mut().ok_or("sparse")?.iter_mut().enumerate() {
            let cell=item.as_object_mut().ok_or("sparse")?;project(cell,&cell_fields,LEVEL==5,&format!("/sparseOverride/{}/{i}",pointer(key)),&mut lost);
            let r=integer(cell.get("rowIndex"),"coordinate")?;let c=integer(cell.get("colIndex"),"coordinate")?;
            require(r>=0 && c>=0 && shape.is_none_or(|(rows,cols)| (r as usize)<rows && (c as usize)<cols),"coordinate")?;
            let rs=if cell.contains_key("rowSpan"){integer(cell.get("rowSpan"),"span")?}else{1};
            let cs=if cell.contains_key("colSpan"){integer(cell.get("colSpan"),"span")?}else{1};
            require(rs>0 && cs>0 && (rs as i64)*(cs as i64)<=100000 && shape.is_none_or(|(rows,cols)|r as i64+rs as i64<=rows as i64 && c as i64+cs as i64<=cols as i64),"span")?;
            if rs>1 || cs>1 {for y in 0..rs {for x in 0..cs {require(occupied.insert((r as i64+y as i64,c as i64+x as i64)),"merge-overlap")?;}}}
            for (k,v) in cell.iter().filter(|(k,_)|cell_fields.contains(k.as_str())) {
                match k.as_str() {
                    "valueNumeric"=>require(v.as_f64().is_some_and(f64::is_finite),"cell-type")?,
                    "imageZoomable"|"videoControls"|"videoMuted"|"videoLoop"=>require(v.is_boolean(),"cell-type")?,
                    "mathAst"=>require(v.is_object(),"expression")?,
                    "rowIndex"|"colIndex"|"rowSpan"|"colSpan"=>{},
                    _=>require(v.is_string(),"cell-type")?,
                }
            }
        }}
    }}
    if LEVEL>=2 {if let Some(types)=table.get("sparseOverrideTypes") {
        for (_,v) in types.as_object().ok_or("type-hint")? {require(v.as_str().is_some_and(|s|["text","number","date","boolean","formula","image"].contains(&s)),"type-hint")?;}
    }}
    if LEVEL>=3 {if let Some(book)=table.get("stylebook") {
        for(_,v)in book.as_object().ok_or("style")? {
            let s=v.as_object().ok_or("style")?;
            if s.contains_key("weight") {let n=integer(s.get("weight"),"style")?;require((0..=1000).contains(&n),"style")?;}
            if let Some(a)=s.get("align") {require(a.as_str().is_some_and(|s|["left","right","center","justify","decimal"].contains(&s)),"style")?;}
            if let Some(f)=s.get("numFormat") {require(f.is_string(),"style")?;}
        }
    }}
    if LEVEL>=4 {if let Some(scale)=table.get("dataBarScale") {
        let s=scale.as_object().ok_or("scale")?;
        for k in ["min","max","zero"] {if let Some(v)=s.get(k) {require(v.as_f64().is_some_and(f64::is_finite),"scale")?;}}
        let min=s.get("min").and_then(Value::as_f64).unwrap_or(-100.0);let max=s.get("max").and_then(Value::as_f64).unwrap_or(100.0);let zero=s.get("zero").and_then(Value::as_f64).unwrap_or(0.0);
        require(min<max && zero>=min && zero<=max,"scale")?;
    }}
    if LEVEL==5 {for k in ["columnPriority","rowPriority","hiddenColumns","hiddenRows"] {if let Some(arr)=table.get(k) {
        let mut seen=BTreeSet::new();for v in arr.as_array().ok_or("visibility")? {let n=integer(Some(v),"visibility")?;
            if k.starts_with("hidden") {require(n>=0 && seen.insert(n) && shape.is_none_or(|(rows,cols)|(n as usize)<if k=="hiddenColumns"{cols}else{rows}),"visibility")?;}
        }
    }}}
    lost.sort();Ok(json!({"ok":true,"table":node,"lost":lost}))
}
// Strict recursive JSON reader: reject duplicates instead of silently taking the last value.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D:Deserializer<'de>>(d:D)->std::result::Result<Self,D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value=Strict;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {write!(f,"JSON")}
            fn visit_bool<E:de::Error>(self,v:bool)->std::result::Result<Strict,E>{Ok(Strict(json!(v)))}
            fn visit_i64<E:de::Error>(self,v:i64)->std::result::Result<Strict,E>{Ok(Strict(json!(v)))}
            fn visit_u64<E:de::Error>(self,v:u64)->std::result::Result<Strict,E>{Ok(Strict(json!(v)))}
            fn visit_f64<E:de::Error>(self,v:f64)->std::result::Result<Strict,E>{if !v.is_finite(){return Err(E::custom("nonfinite"));}Ok(Strict(json!(v)))}
            fn visit_str<E:de::Error>(self,v:&str)->std::result::Result<Strict,E>{Ok(Strict(json!(v)))}
            fn visit_unit<E:de::Error>(self)->std::result::Result<Strict,E>{Ok(Strict(Value::Null))}
            fn visit_none<E:de::Error>(self)->std::result::Result<Strict,E>{Ok(Strict(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->std::result::Result<Strict,A::Error>{let mut v=vec![];while let Some(Strict(x))=a.next_element()?{v.push(x);}Ok(Strict(Value::Array(v)))}
            fn visit_map<A:MapAccess<'de>>(self,mut a:A)->std::result::Result<Strict,A::Error>{let mut m=Map::new();while let Some((k,Strict(v)))=a.next_entry::<String,Strict>()?{if m.insert(k,v).is_some(){return Err(de::Error::custom("duplicate"));}}Ok(Strict(Value::Object(m)))}
        }
        d.deserialize_any(V)
    }
}
fn main() {
    for line in io::stdin().lock().lines() {let line=line.expect("stdin");
        let result=serde_json::from_str::<Strict>(&line).map_err(|_|"json").and_then(|Strict(v)|process(v));
        let value=match result {Ok(v)=>v,Err(e)=>json!({"ok":false,"error":e})};println!("{value}");
    }
}
