#!/usr/bin/env python3
"""D2b — 값 실재 검사 (정밀판).

겨냥: 스토리가 **게시물의 형태라고 주장하는 것**이 계약에 실재하는가.
C-1(`value_formatted`)이 D2a 를 통과한 이유가 이것이다.

대상 = ① 스토리의 json/jsonc 코드블록 안의 키   ② `artifact.field` 형태의 점 경로 인용
       ③ ts/tsx/js 코드블록의 `<식별자>.<프로퍼티>` 접근  (Thomas NR-4)

③ 이 없으면 이 도구의 창립 사례(C-1 `m.value_formatted`)를 자기가 못 잡는다.
"""
import json, re, pathlib
ROOT = pathlib.Path('/Users/otter/72offsuit/AI_ROI')
STORY = ROOT/'.agent-team/03-story-engineering'
SCH = ROOT/'.agent-team/04-architecture/schemas'

props, enums = set(), set()
def walk(n):
    if isinstance(n, dict):
        for k,v in n.items():
            if k=='properties' and isinstance(v,dict): props.update(v.keys())
            if k=='enum' and isinstance(v,list): enums.update(str(x) for x in v)
            if k=='const': enums.add(str(v))
            walk(v)
    elif isinstance(n,list):
        for x in n: walk(x)
for f in SCH.glob('*.json'): walk(json.load(open(f)))

fx=set()
def fw(n):
    if isinstance(n,dict):
        fx.update(n.keys())
        for v in n.values(): fw(v)
    elif isinstance(n,list):
        for x in n: fw(x)
for f in (ROOT/'.agent-team/04-architecture/examples').rglob('*.json'): fw(json.load(open(f)))

META = {  # JSON Schema 메타 키워드 — 게시물 키가 아니다
 'type','enum','const','not','if','then','else','required','properties','description','$comment',
 'items','minLength','maxLength','minimum','maximum','pattern','format','anyOf','allOf','oneOf',
 'additionalProperties','minProperties','maxProperties','minItems','maxItems','$ref','$defs',
 '$schema','$id','title','default','examples','uniqueItems','nullable','propertyNames',
}
EXT = {  # 파일 확장자 — 점 경로가 아니다
 'py','md','json','jsonc','yaml','yml','mjs','js','ts','tsx','css','txt','toml','parquet',
 'jsonl','gz','lock','cfg','ini','sh','html','svg','png','schema','config','generated','mjs',
}
# sink.manifest() 키 · IngestResult 필드 — 계약이 아니라 코드가 정본
SINK = set()
import ast as _ast
_src = (ROOT/'src/measurement/sink.py').read_text(encoding='utf-8')
for _n in _ast.walk(_ast.parse(_src)):
    if isinstance(_n, _ast.Constant) and isinstance(_n.value, str) and _n.value.isidentifier():
        SINK.add(_n.value)
    if isinstance(_n, _ast.AnnAssign) and isinstance(_n.target, _ast.Name):
        SINK.add(_n.target.id)

PYMOD = {'src','tests','json','os','self','result','freeze','sys','re','pathlib','yaml','typing'}
NPM = {'scripts','dev','build','start','lint','test','prebuild','predev','tokens'}

KNOWN = props | fx | SINK
print("D2b 정밀 — 게시물 형태 주장 검사")
print(f"  계약 프로퍼티 {len(props)} · enum 값 {len(enums)} · 픽스처 키 {len(fx)}\n")

miss_keys, miss_enums, n_key, n_enum = [], [], 0, 0
for sf in sorted(STORY.glob('story-*.md')):
    txt = sf.read_text(encoding='utf-8')
    # ① json/jsonc 코드블록의 키
    for blk in re.findall(r'```jsonc?\n(.*?)```', txt, re.S):
        for k in set(re.findall(r'"([a-z][a-z0-9_]*)"\s*:', blk)):
            n_key += 1
            if k not in KNOWN and k not in META and k not in NPM:
                line = next((l.strip() for l in blk.split('\n') if f'"{k}"' in l), '')
                miss_keys.append((sf.name, k, line[:100]))
        # 블록 안 문자열 리터럴 중 대문자 상수형 = enum 후보
        for e in set(re.findall(r'"([A-Z][A-Z0-9_]{3,})"', blk)):
            n_enum += 1
            if e not in enums:
                miss_enums.append((sf.name, e))
    # ② artifact.field 점 경로
    for dotted in set(re.findall(r'`([a-z_]+(?:_report|_status|index|manifest)?)\.([a-z_]+(?:\.[a-z_]+)*)`', txt)):
        base, rest = dotted
        for part in rest.split('.'):
            if part and not part.isdigit():
                n_key += 1
                if part not in KNOWN and part not in EXT and part not in META and base not in PYMOD:
                    miss_keys.append((sf.name, f"{base}.{part}", "점 경로 인용"))

seen=set(); out=[]
for a,b,c in miss_keys:
    if (a,b) in seen: continue
    seen.add((a,b)); out.append((a,b,c))
print(f"  ① 게시물 키 {n_key}종 검사 → 계약·픽스처에 없는 것 {len(out)}건")
for a,b,c in sorted(out): print(f"    {a[:34]:<34} `{b}`   {c}")
print()
seen=set(); oe=[]
for a,b in miss_enums:
    if (a,b) in seen: continue
    seen.add((a,b)); oe.append((a,b))
print(f"  ② enum 값 {n_enum}종 검사 → 계약 enum 에 없는 것 {len(oe)}건")
for a,b in sorted(oe): print(f"    {a[:34]:<34} `{b}`")

# ── ③ ts/tsx/js 코드블록의 프로퍼티 접근 (Thomas NR-4) ────────────────────
JS_HOST = {  # 데이터가 아닌 호스트/전역 객체
 'console','Math','JSON','Object','Array','String','Number','Boolean','Date','Promise',
 'process','window','document','globalThis','React','Intl','Number','Map','Set','fs','path',
 'os','crypto','Error','RegExp','Symbol','BigInt','navigator','localStorage','performance',
}
JS_METHOD = {  # 언어/표준 라이브러리 메서드·프로퍼티
 'map','filter','reduce','forEach','find','findIndex','some','every','sort','reverse','slice',
 'splice','push','pop','shift','unshift','concat','join','includes','indexOf','lastIndexOf',
 'length','keys','values','entries','toString','valueOf','trim','split','replace','replaceAll',
 'startsWith','endsWith','padStart','padEnd','match','test','exec','toFixed','toLocaleString',
 'then','catch','finally','all','race','json','text','parse','stringify','freeze','assign',
 'from','of','has','get','set','add','delete','clear','toUpperCase','toLowerCase','flat',
 'flatMap','at','fill','repeat','charAt','substring','substr','toISOString','getTime','now',
 'log','warn','error','info','debug','env','argv','exit','resolve','reject','bind','call',
 'apply','default','props','children','current','style','className','key','ref',
}

miss_js, n_js = [], 0
for sf in sorted(STORY.glob('story-*.md')):
    txt = sf.read_text(encoding='utf-8')
    for blk in re.findall(r'```(?:ts|tsx|js|jsx|javascript|typescript)\n(.*?)```', txt, re.S):
        blk = re.sub(r'//[^\n]*', '', blk)          # 줄 주석 제거
        blk = re.sub(r'/\*.*?\*/', '', blk, flags=re.S)
        for base, prop in set(re.findall(r'\b([A-Za-z_$][\w$]*)\.([a-z][A-Za-z0-9_]*)\b', blk)):
            if base in JS_HOST or prop in JS_METHOD:
                continue
            n_js += 1
            if prop not in KNOWN and prop not in enums and prop not in EXT and prop not in META:
                line = next((l.strip() for l in blk.split('\n') if f'{base}.{prop}' in l), '')
                miss_js.append((sf.name, f'{base}.{prop}', line[:100]))

seen=set(); oj=[]
for a,b,c in miss_js:
    if (a,b) in seen: continue
    seen.add((a,b)); oj.append((a,b,c))
print()
print(f"  \u2462 ts/tsx/js \ud504\ub85c\ud37c\ud2f0 \uc811\uadfc {n_js}\uac74 \uac80\uc0ac \u2192 \uacc4\uc57d\u00b7\ud53d\uc2a4\ucc98\uc5d0 \uc5c6\ub294 \uac83 {len(oj)}\uac74")
for a,b,c in sorted(oj): print(f"    {a[:34]:<34} `{b}`   {c}")
