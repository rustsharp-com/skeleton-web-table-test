// Reconstructed demonstration binding, not a historical production release.
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Encodings.Web;

static class Adapter {
    static readonly JsonSerializerOptions Options = new() { Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
    static readonly string[][] Roots = {
        new[]{"tableId","tableName","title","stringValues","numericValues"},
        new[]{"columns","rows","styleMatrix"},
        new[]{"sparseOverride","sparseOverrideTypes"},
        new[]{"stylebook","fontConfig"},
        new[]{"imageManager","cellBackgroundImageRefs","cellIds","dataBarScale","cellDataBars","captureTokens"},
        new[]{"columnPriority","rowPriority","hiddenColumns","hiddenRows"}
    };
    static readonly string[] Forbidden = {"allStylesLight","allStylesDark","allStylesExtra","themes"};
    static void Require(bool ok, string code) { if (!ok) throw new InvalidDataException(code); }
    static bool Str(JsonNode? n) => n is JsonValue v && v.TryGetValue<string>(out _);
    static bool Num(JsonNode? n) => n is JsonValue v && v.TryGetValue<double>(out var d) && double.IsFinite(d);
    static int Integer(JsonNode? n, string code) {
        Require(Num(n), code); double d=n!.GetValue<double>();
        Require(d==Math.Truncate(d) && d>=int.MinValue && d<=int.MaxValue, code); return (int)d;
    }
    static string Pointer(string key) => key.Replace("~","~0").Replace("/","~1");
    static void Unique(JsonElement e) {
        if(e.ValueKind==JsonValueKind.Object) {
            var keys=new HashSet<string>();
            foreach(var p in e.EnumerateObject()) { Require(keys.Add(p.Name),"json"); Unique(p.Value); }
        } else if(e.ValueKind==JsonValueKind.Array) foreach(var x in e.EnumerateArray()) Unique(x);
    }
    static void Project(JsonObject obj, HashSet<string> fields, bool extra, string path, List<string> lost) {
        foreach(var key in obj.Select(p=>p.Key).ToArray()) {
            if((!fields.Contains(key) && !extra) || (fields.Contains(key) && obj[key] is null)) {
                obj.Remove(key); lost.Add(path+"/"+Pointer(key));
            }
        }
    }
    static void Metadata(JsonObject table,string name,bool column,List<string> lost) {
        if(table[name] is not JsonNode node) return;
        Require(node is JsonArray,"metadata");
        var fields=new HashSet<string>(column ? new[]{"id","header","typeHint","width","alignment"} : new[]{"id","header","height"});
        if(Profile.Level==5) { fields.Add(column?"widthExpr":"heightExpr"); fields.Add("hidden"); }
        int i=0;
        foreach(var item in (JsonArray)node) {
            Require(item is JsonObject,"metadata"); var row=(JsonObject)item!;
            Project(row,fields,Profile.Level==5,$"/{name}/{i++}",lost);
            foreach(var key in fields) if(row[key] is JsonNode value) {
                if(key=="hidden") Require(value is JsonValue v && v.TryGetValue<bool>(out _),"metadata");
                else if(key.EndsWith("Expr")) Require(value is JsonObject,"expression");
                else Require(Str(value),"metadata");
            }
        }
    }
    public static JsonObject Process(string line) {
        try {
            using var doc=JsonDocument.Parse(line,new JsonDocumentOptions{MaxDepth=64}); Unique(doc.RootElement);
            var node=JsonNode.Parse(line); Require(node is JsonObject,"table"); var table=(JsonObject)node!;
            var lost=new List<string>();
            if(Profile.Level>=3) Require(!Forbidden.Any(table.ContainsKey),"forbidden-key");
            var fields=Roots.Take(Profile.Level+1).SelectMany(x=>x).ToHashSet();
            Project(table,fields,Profile.Level>=3,"",lost);
            foreach(var key in new[]{"tableId","tableName","title"}) if(table[key] is JsonNode n) Require(Str(n),"identity");
            int? rows=null,cols=null;
            foreach(var key in new[]{"stringValues","numericValues","styleMatrix"}.Where(fields.Contains)) {
                if(table[key] is not JsonNode grid) continue; Require(grid is JsonArray,"grid-shape");
                int r=((JsonArray)grid).Count,c=-1;
                foreach(var row in (JsonArray)grid) {
                    Require(row is JsonArray,"grid-shape"); var a=(JsonArray)row!;
                    if(c<0)c=a.Count; Require(a.Count==c,"grid-shape");
                    foreach(var value in a) Require(value is null || (key=="numericValues" ? Num(value) : Str(value)),"cell-type");
                }
                c=Math.Max(0,c); Require(rows is null || (rows==r && cols==c),"grid-shape"); rows=r;cols=c;
            }
            if(Profile.Level>=1) { Metadata(table,"columns",true,lost);Metadata(table,"rows",false,lost); }
            if(Profile.Level>=2 && table["sparseOverride"] is JsonNode sparse) {
                Require(sparse is JsonObject,"sparse"); var occupied=new HashSet<(int,int)>();
                var cellFields=new HashSet<string>(new[]{"rowIndex","colIndex","rowSpan","colSpan","value","valueNumeric","styleKey","typeRef","formula","formatString"});
                if(Profile.Level>=4) cellFields.UnionWith(new[]{"imageRef","imageAlt","imageFit","imageZoomable","videoRef","posterRef","videoControls","videoMuted","videoLoop","videoFit","mathTex","mathAst"});
                foreach(var entry in (JsonObject)sparse) {
                    Require(entry.Value is JsonArray,"sparse"); int i=0;
                    foreach(var item in (JsonArray)entry.Value!) {
                        Require(item is JsonObject,"sparse"); var cell=(JsonObject)item!;
                        Project(cell,cellFields,Profile.Level==5,"/sparseOverride/"+Pointer(entry.Key)+"/"+i++,lost);
                        int r=Integer(cell["rowIndex"],"coordinate"),c=Integer(cell["colIndex"],"coordinate");
                        Require(r>=0 && c>=0 && (rows is null || (r<rows && c<cols)),"coordinate");
                        int rs=cell["rowSpan"] is null?1:Integer(cell["rowSpan"],"span"),cs=cell["colSpan"] is null?1:Integer(cell["colSpan"],"span");
                        Require(rs>0 && cs>0 && (long)rs*cs<=100000 && (rows is null || ((long)r+rs<=rows && (long)c+cs<=cols)),"span");
                        if(rs>1 || cs>1) for(int y=0;y<rs;y++) for(int x=0;x<cs;x++) Require(occupied.Add((r+y,c+x)),"merge-overlap");
                        foreach(var p in cell.Where(p=>cellFields.Contains(p.Key))) {
                            if(new[]{"valueNumeric"}.Contains(p.Key)) Require(Num(p.Value),"cell-type");
                            else if(new[]{"imageZoomable","videoControls","videoMuted","videoLoop"}.Contains(p.Key)) Require(p.Value is JsonValue v && v.TryGetValue<bool>(out _),"cell-type");
                            else if(p.Key=="mathAst") Require(p.Value is JsonObject,"expression");
                            else if(!new[]{"rowIndex","colIndex","rowSpan","colSpan"}.Contains(p.Key)) Require(Str(p.Value),"cell-type");
                        }
                    }
                }
            }
            if(Profile.Level>=2 && table["sparseOverrideTypes"] is JsonNode types) {
                Require(types is JsonObject,"type-hint");
                foreach(var p in (JsonObject)types) Require(Str(p.Value) && new[]{"text","number","date","boolean","formula","image"}.Contains(p.Value!.GetValue<string>()),"type-hint");
            }
            if(Profile.Level>=3 && table["stylebook"] is JsonNode book) {
                Require(book is JsonObject,"style"); foreach(var p in (JsonObject)book) {
                    Require(p.Value is JsonObject,"style"); var style=(JsonObject)p.Value!;
                    if(style["weight"] is JsonNode w) { int n=Integer(w,"style");Require(n>=0 && n<=1000,"style"); }
                    if(style["align"] is JsonNode a) Require(Str(a) && new[]{"left","right","center","justify","decimal"}.Contains(a.GetValue<string>()),"style");
                    if(style["numFormat"] is JsonNode f) Require(Str(f),"style");
                }
            }
            if(Profile.Level>=4 && table["dataBarScale"] is JsonNode scale) {
                Require(scale is JsonObject,"scale"); var s=(JsonObject)scale;
                foreach(var k in new[]{"min","max","zero"}) if(s[k] is JsonNode v) Require(Num(v),"scale");
                double min=s["min"]?.GetValue<double>()??-100,max=s["max"]?.GetValue<double>()??100,zero=s["zero"]?.GetValue<double>()??0;
                Require(min<max && zero>=min && zero<=max,"scale");
            }
            if(Profile.Level==5) foreach(var key in new[]{"columnPriority","rowPriority","hiddenColumns","hiddenRows"}) {
                if(table[key] is not JsonNode arr) continue; Require(arr is JsonArray,"visibility");
                var seen=new HashSet<int>(); foreach(var v in (JsonArray)arr) { int n=Integer(v,"visibility");
                    if(key.StartsWith("hidden")) Require(n>=0 && seen.Add(n) && (rows is null || n<(key=="hiddenColumns"?cols:rows)),"visibility");
                }
            }
            lost.Sort(StringComparer.Ordinal);
            return new JsonObject{{"ok",true},{"table",table},{"lost",JsonSerializer.SerializeToNode(lost)}};
        } catch(InvalidDataException e) { return new JsonObject{{"ok",false},{"error",e.Message}}; }
        catch(JsonException) { return new JsonObject{{"ok",false},{"error","json"}}; }
    }
    static void Main() {
        Console.InputEncoding=new System.Text.UTF8Encoding(false);
        Console.OutputEncoding=new System.Text.UTF8Encoding(false);
        string? line;while((line=Console.ReadLine())!=null) Console.WriteLine(Process(line).ToJsonString(Options));
    }
}
