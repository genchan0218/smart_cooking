import requests, re, json, time, sys, random
h={"User-Agent":"Mozilla/5.0 (personal recipe app; contact via owner) "}
limit=int(sys.argv[1]); out=sys.argv[2]
sm=requests.get("https://www.justonecookbook.com/post-sitemap.xml",headers=h,timeout=60).text
urls=re.findall(r"<loc>([^<]+)</loc>",sm)
random.Random(1).shuffle(urls)
def find_recipe(node):
    if isinstance(node,list):
        for n in node:
            r=find_recipe(n)
            if r: return r
    elif isinstance(node,dict):
        t=node.get("@type"); t=t if isinstance(t,list) else [t]
        if "Recipe" in t: return node
        return find_recipe(node.get("@graph",[]))
res=[]; tried=0
for u in urls:
    if len(res)>=limit or tried>=limit*3: break
    tried+=1
    try: html=requests.get(u,headers=h,timeout=30).text
    except Exception: continue
    for blk in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>',html,re.S):
        try: r=find_recipe(json.loads(blk))
        except Exception: continue
        if r:
            def lst(x): return x if isinstance(x,list) else ([x] if x else [])
            res.append({"source":"justonecookbook","cuisine":"Japanese","name":r.get("name"),"url":u,
              "ingredients":r.get("recipeIngredient",[]),"category":lst(r.get("recipeCategory")),
              "total_time":r.get("totalTime"),"yield":r.get("recipeYield"),"keywords":r.get("keywords")})
            break
    time.sleep(1)
    if tried%20==0: print(tried,len(res),flush=True)
json.dump(res,open(out,"w",encoding="utf-8"),ensure_ascii=False,indent=1)
print("done",tried,len(res))
