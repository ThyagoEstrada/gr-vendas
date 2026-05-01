-- Adicionar colunas de pedido programado
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS tipo varchar(20) DEFAULT 'Normal';
ALTER TABLE pedidos ADD COLUMN IF NOT EXISTS data_entrega date;

-- Índice para buscas por data de entrega
CREATE INDEX IF NOT EXISTS idx_pedidos_data_entrega ON pedidos (data_entrega)
  WHERE data_entrega IS NOT NULL;

-- Índice para filtrar por tipo
CREATE INDEX IF NOT EXISTS idx_pedidos_tipo ON pedidos (tipo);
