"""
GR VENDAS — Transcrição de Voz para Pedidos
=============================================
Transcreve áudios e cadastra pedidos automaticamente no Supabase.

INSTALAÇÃO (apenas uma vez):
  pip install openai-whisper requests torch

PADRÃO DE DITADO:
  "Novo pedido, cliente NOME DO CLIENTE, valor VALOR, tabela TABELA PERCENTUAL."

  Exemplos:
    "Novo pedido, cliente SR Metalurgica, valor 3689,00, tabela D 3,5."
    "Novo pedido, data 31 do 03, cliente Bassano Alimentos, valor 7 mil 669 e 20, tabela D 3,5."
    "Novo pedido, cliente Granja Rio Claro, valor 73 mil 700, tabela 125 D 2."

  Dicas:
    - Diga "novo pedido" para separar os pedidos
    - A data é opcional — se omitir, usa a data de hoje
    - Valores: "980", "1 mil 250", "7 mil 669 e 20" (centavos)
    - Tabelas: "A 2", "D 3,5", "108 D 4,5"
    - Pode gravar vários pedidos num mesmo áudio
"""

import os, re, sys, json, requests
from datetime import date, datetime
from difflib import SequenceMatcher

# ── CONFIGURAÇÃO ──────────────────────────────────────────────────────────────
SUPABASE_URL = "https://lbrhckgeuigxlpaouyff.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxicmhja2dldWlneGxwYW91eWZmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3OTE1NzcsImV4cCI6MjA5MjM2NzU3N30.77oF1jiMcYFBVyRAvmQ8OWdeNz-vmlVL-A1HdXLUmLA"
HEADERS = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer": "return=representation"
}
ANO_PADRAO = date.today().year
MESES = {
    'janeiro':1,'fevereiro':2,'março':3,'marco':3,'abril':4,'maio':5,'junho':6,
    'julho':7,'agosto':8,'setembro':9,'outubro':10,'novembro':11,'dezembro':12,
    'jan':1,'fev':2,'mar':3,'abr':4,'mai':5,'jun':6,
    'jul':7,'ago':8,'set':9,'out':10,'nov':11,'dez':12
}

# ── SUPABASE ──────────────────────────────────────────────────────────────────
def sb_get(tabela, query=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabela}{query}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def sb_post(tabela, data):
    r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"  ⚠️  Erro: {r.text[:200]}")
        return None
    return r.json()

# ── TRANSCRIÇÃO WHISPER ───────────────────────────────────────────────────────
def transcrever(caminho):
    try:
        import whisper
    except ImportError:
        print("\n❌ Whisper não instalado! Execute:")
        print("   pip install openai-whisper torch")
        sys.exit(1)
    print("   🔄 Carregando modelo Whisper (primeira vez faz download ~460MB)...")
    model = whisper.load_model("small")
    print("   🎙️  Transcrevendo...")
    result = model.transcribe(caminho, language="pt", fp16=False)
    texto = result["text"].strip()
    print(f"\n   📝 Transcrição:")
    print(f"   {'─'*55}")
    print(f"   {texto}")
    print(f"   {'─'*55}")
    return texto

# ── PARSER ────────────────────────────────────────────────────────────────────
def split_campos(bloco):
    """Divide por vírgula protegendo números como '3,5' e '3689,00'."""
    protegido = re.sub(r'(\d),(\d)', r'\1§\2', bloco)
    partes = [p.strip() for p in protegido.split(',')]
    return [p.replace('§', ',') for p in partes]

def parse_valor(t):
    t = t.lower().strip()
    cent = 0.0
    m = re.search(r'\be\s+(\d{1,2})\s*(?:centavos?)?\s*$', t)
    if m:
        cn = int(m.group(1))
        cent = cn/100 if cn >= 10 else cn/10
        t = t[:m.start()].strip()
    v = 0.0
    m = re.search(r'(\d+)\s*milh[ãa]o', t)
    if m:
        v += float(m.group(1))*1_000_000
        t = re.sub(r'\d+\s*milh[ãa]o','',t).strip()
    m = re.search(r'(\d+)\s*mil', t)
    if m:
        v += float(m.group(1))*1000
        t = re.sub(r'\d+\s*mil','',t).strip()
    m = re.search(r'(\d+(?:[.,]\d+)?)', t)
    if m:
        try: v += float(m.group(1).replace(',','.'))
        except: pass
    return round(v + cent, 2)

def parse_data(t, ano=ANO_PADRAO):
    tl = t.lower().strip()
    m = re.match(r'(\d{1,2})\s+d[oe]\s+(\d{1,2})(?!\d)', tl)
    if m:
        d,ms = int(m.group(1)),int(m.group(2))
        if 1<=d<=31 and 1<=ms<=12:
            return f"{ano}-{ms:02d}-{d:02d}"
    for nome,num in MESES.items():
        m2 = re.match(rf'(\d{{1,2}})\s+de\s+{nome}(?!\w)', tl)
        if m2:
            d = int(m2.group(1))
            if 1<=d<=31: return f"{ano}-{num:02d}-{d:02d}"
    if 'hoje' in tl: return date.today().strftime('%Y-%m-%d')
    return None

def parse_tabela(t):
    t = re.sub(r'^tab(?:ela)?\s*','', t.lower().strip())
    m = re.match(r'(\d{2,4})\s+d\s*(\d+(?:[.,]\d+)?)', t)
    if m: return m.group(1), float(m.group(2).replace(',','.'))
    m = re.match(r'([a-f])\s+(\d+(?:[.,]\d+)?)', t)
    if m: return m.group(1).upper(), float(m.group(2).replace(',','.'))
    m = re.match(r'([a-f]|\d{2,4})\s+x', t)
    if m: return m.group(1).upper(), 0.0
    return '', 0.0

def parse_pedido(bloco, ano=ANO_PADRAO):
    bloco = re.sub(r'\s+', ' ', bloco.lower()).strip()
    if len(bloco) < 5: return None
    res = dict(data=date.today().strftime('%Y-%m-%d'),
               cliente_raw='', cliente_id=None, cliente_nome='',
               valor=0.0, tabela='', percentual=0.0, match_score=0)
    for parte in split_campos(bloco):
        parte = parte.strip()
        if not parte: continue
        if parte.startswith('data '):
            d = parse_data(parte[5:], ano)
            if d: res['data'] = d
        elif re.match(r'\d{1,2}\s+d[oe]\s+\d{1,2}', parte):
            d = parse_data(parte, ano)
            if d: res['data'] = d
        elif parte.startswith('cliente '):
            cli = parte[8:].strip().upper()
            res['cliente_raw'] = cli
            res['cliente_nome'] = cli
        elif re.match(r'v(?:alor)?\s+', parte):
            res['valor'] = parse_valor(re.sub(r'^v(?:alor)?\s+','',parte))
        elif re.match(r'tab(?:ela)?\s+', parte):
            tab,pct = parse_tabela(re.sub(r'^tab(?:ela)?\s+','',parte))
            res['tabela'] = tab
            res['percentual'] = pct
    if not res['cliente_raw'] or res['valor'] <= 0: return None
    return res

def parse_pedidos_audio(texto, ano=ANO_PADRAO):
    t = re.sub(r'\s+', ' ', texto.lower()).strip()
    blocos = re.split(r'novo\s+pedido|pr[oó]ximo\s+pedido', t)
    return [p for b in blocos if (p := parse_pedido(b, ano))]

# ── FUZZY MATCH DE CLIENTES ───────────────────────────────────────────────────
def buscar_cliente(nome, clientes_db):
    nome = nome.upper().strip()
    melhor, score = None, 0
    for c in clientes_db:
        db = c['nome'].upper().strip()
        if nome == db: return c, 1.0
        if nome in db or db in nome: s = 0.9
        else: s = SequenceMatcher(None, nome, db).ratio()
        pf = set(nome.split())
        pd = set(db.split())
        if pf and pf.issubset(pd): s = max(s, 0.85)
        if s > score: score = s; melhor = c
    return melhor, score

def resolver_clientes(pedidos, clientes_db):
    for p in pedidos:
        c, score = buscar_cliente(p['cliente_raw'], clientes_db)
        if c and score >= 0.60:
            p['cliente_id'] = c['id']
            p['cliente_nome'] = c['nome']
            p['match_score'] = score
            if score < 0.85:
                print(f"  ⚠️  Match parcial ({score:.0%}): '{p['cliente_raw']}' → '{c['nome']}'")
        else:
            p['cliente_id'] = None
            p['match_score'] = 0
            print(f"  ❌ Cliente não encontrado: '{p['cliente_raw']}'")
    return pedidos

# ── EXIBIR E CONFIRMAR ────────────────────────────────────────────────────────
def confirmar(pedidos):
    ok  = [p for p in pedidos if p['cliente_id']]
    nok = [p for p in pedidos if not p['cliente_id']]
    print(f"\n{'─'*65}")
    print(f"  {'#':>3}  {'Data':>10}  {'Cliente':<30}  {'Valor':>10}  Tab")
    print(f"{'─'*65}")
    for i,p in enumerate(ok,1):
        sc = f" ({p['match_score']:.0%})" if p['match_score']<0.95 else ""
        print(f"  {i:>3}  {p['data']:>10}  {p['cliente_nome'][:30]:<30}  R${p['valor']:>9,.2f}  {p['tabela']} {p['percentual']}%{sc}")
    if nok:
        print(f"\n  ⚠️  Sem cliente encontrado ({len(nok)}):")
        for p in nok:
            print(f"       → '{p['cliente_raw']}' — R$ {p['valor']:,.2f}")
    print(f"{'─'*65}")
    print(f"  Total: {len(ok)} pedido(s) | R$ {sum(p['valor'] for p in ok):,.2f}")
    if nok: print(f"  {len(nok)} pedido(s) serão ignorados")
    print(f"{'─'*65}")
    return input("\n  Confirmar e salvar? (s/n): ").strip().lower() == 's'

# ── SALVAR ────────────────────────────────────────────────────────────────────
def salvar(pedidos):
    salvos = erros = 0
    for p in pedidos:
        if not p['cliente_id']: continue
        r = sb_post('pedidos', {
            'data_pedido': p['data'],
            'cliente_id': p['cliente_id'],
            'valor_total': p['valor'],
            'status': 'Pendente',
            'observacao': f"Áudio | Tab: {p['tabela']} {p['percentual']}%"
        })
        if r: salvos += 1; print(f"  ✅ {p['cliente_nome'][:40]} — R$ {p['valor']:,.2f}")
        else: erros += 1
    return salvos, erros

# ── PROCESSAR ÁUDIO ───────────────────────────────────────────────────────────
def processar(caminho, clientes_db, ano):
    print(f"\n{'='*65}")
    print(f"  🎙️  {os.path.basename(caminho)}")
    print(f"{'='*65}")
    texto = transcrever(caminho)
    pedidos = parse_pedidos_audio(texto, ano)
    print(f"\n  📦 {len(pedidos)} pedido(s) identificado(s)")
    if not pedidos:
        print("  ⚠️  Nenhum pedido. Verifique se usou o padrão correto.")
        return 0, 0
    print(f"\n  👤 Buscando clientes...")
    pedidos = resolver_clientes(pedidos, clientes_db)
    if not confirmar(pedidos):
        print("  ❌ Cancelado."); return 0, 0
    print(f"\n  💾 Salvando...")
    s, e = salvar(pedidos)
    print(f"\n  ✅ {s} salvo(s) | ❌ {e} erro(s)")
    return s, e

# ── MENU ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("  GR VENDAS — Transcrição de Voz para Pedidos")
    print("=" * 65)
    print("\n  PADRÃO DE DITADO:")
    print("  'Novo pedido, cliente NOME, valor VALOR, tabela TAB PERC.'")
    print("  Ex: 'Novo pedido, cliente SR Metalurgica, valor 3689,00, tabela D 3,5.'")
    print()

    print("🔌 Conectando ao banco...")
    try:
        clientes_db = sb_get('clientes','?select=id,codigo,nome&status=eq.ativo&order=nome')
        print(f"  ✅ {len(clientes_db)} clientes carregados")
    except Exception as e:
        print(f"  ❌ Erro: {e}"); input("\nEnter para sair..."); return

    ano_s = input(f"\nAno dos pedidos [{ANO_PADRAO}]: ").strip()
    ano = int(ano_s) if ano_s.isdigit() else ANO_PADRAO

    print("\nOpções:")
    print("  1 — Processar um arquivo de áudio")
    print("  2 — Processar todos os áudios de uma pasta")
    print("  3 — Testar digitando o texto (sem áudio)")
    print("  4 — Sair")
    op = input("\nOpção: ").strip()

    if op == '1':
        c = input("Caminho do arquivo (.m4a/.mp3/.wav): ").strip().strip('"')
        if os.path.isfile(c): processar(c, clientes_db, ano)
        else: print(f"❌ Não encontrado: {c}")

    elif op == '2':
        pasta = input("Caminho da pasta: ").strip().strip('"')
        if not os.path.isdir(pasta): print(f"❌ Pasta não encontrada"); return
        exts = ('.m4a','.mp3','.wav','.ogg','.aac','.mp4')
        arqs = sorted([f for f in os.listdir(pasta) if f.lower().endswith(exts)])
        if not arqs: print("❌ Nenhum áudio encontrado."); return
        print(f"\n📂 {len(arqs)} arquivo(s):")
        for f in arqs: print(f"  • {f}")
        if input(f"\nProcessar todos? (s/n): ").strip().lower()=='s':
            total = 0
            for f in arqs:
                s,_ = processar(os.path.join(pasta,f), clientes_db, ano)
                total += s
            print(f"\n✅ Total salvo: {total} pedido(s)")

    elif op == '3':
        print("\nDigite o texto (simule a transcrição). FIM para encerrar.\n")
        linhas = []
        while True:
            l = input("  > ")
            if l.strip().upper()=='FIM': break
            linhas.append(l)
        texto = ' '.join(linhas)
        if texto.strip():
            pedidos = parse_pedidos_audio(texto, ano)
            print(f"\n  📦 {len(pedidos)} pedido(s) identificado(s)")
            pedidos = resolver_clientes(pedidos, clientes_db)
            if confirmar(pedidos):
                s,e = salvar(pedidos)
                print(f"\n  ✅ {s} salvo(s) | ❌ {e} erro(s)")

    input("\nEnter para sair...")

if __name__ == '__main__':
    main()
