-- Fila de aprovação de clientes novos detectados nos PDFs
CREATE TABLE IF NOT EXISTS clientes_pendentes (
  id              serial        PRIMARY KEY,
  nome            varchar(200)  NOT NULL,
  codigo          integer,
  cidade          varchar(200),
  origem          varchar(10)   NOT NULL,     -- ENTRADA ou SAIDA
  mes             integer       NOT NULL,
  ano             integer       NOT NULL,
  valor_total     numeric(12,2),
  numero_pedido   varchar(50),
  status          varchar(20)   DEFAULT 'aguardando', -- aguardando / aprovado / ignorado
  observacao      varchar(300),
  created_at      timestamp     DEFAULT now(),
  updated_at      timestamp     DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_clientes_pendentes_status ON clientes_pendentes(status);
CREATE INDEX IF NOT EXISTS idx_clientes_pendentes_mes_ano ON clientes_pendentes(mes, ano);
