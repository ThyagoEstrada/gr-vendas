-- Migração: conferência de entrada/saída
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS data_aprovacao date;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS mes_meta integer;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS ano_meta integer;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS percentual_comissao numeric(5,2);
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS status_entrada varchar(20) DEFAULT 'Pendente';
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS status_saida varchar(20) DEFAULT 'Pendente';
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS valor_entrada numeric(12,2);
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS valor_saida numeric(12,2);
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS comissao_esperada numeric(12,2);
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS comissao_recebida numeric(12,2);

-- Pedidos aprovados existentes recebem data_aprovacao/mes_meta/ano_meta
UPDATE pedidos SET
  data_aprovacao = data_pedido,
  mes_meta = extract(month from data_pedido)::int,
  ano_meta = extract(year from data_pedido)::int
WHERE status IN ('Aprovado','Importado','Faturado')
  AND data_aprovacao IS NULL;

CREATE INDEX IF NOT EXISTS idx_pedidos_mes_meta ON pedidos(ano_meta, mes_meta);
CREATE INDEX IF NOT EXISTS idx_pedidos_status_entrada ON pedidos(status_entrada);
CREATE INDEX IF NOT EXISTS idx_pedidos_status_saida ON pedidos(status_saida);
