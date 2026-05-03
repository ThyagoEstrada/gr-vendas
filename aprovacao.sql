-- Migração: fluxo de aprovação de pedidos
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS data_aprovacao date;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS mes_meta integer;
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS ano_meta integer;

-- Pedidos já aprovados recebem data_aprovacao = data_pedido e mes/ano_meta
UPDATE pedidos
SET data_aprovacao = data_pedido,
    mes_meta = extract(month from data_pedido)::int,
    ano_meta = extract(year from data_pedido)::int
WHERE status IN ('Aprovado','Importado','Faturado');
