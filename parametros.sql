-- Tabela de parâmetros configuráveis do sistema GR Vendas
CREATE TABLE IF NOT EXISTS parametros (
  chave       varchar(50)  PRIMARY KEY,
  valor       varchar(200) NOT NULL,
  descricao   varchar(300),
  tipo        varchar(20)  DEFAULT 'texto',
  updated_at  timestamp    DEFAULT now()
);

INSERT INTO parametros (chave, valor, descricao, tipo) VALUES
  ('meta_mensal',           '370000', 'Meta mensal de vendas em R$',                                                          'numero'),
  ('dias_antes_meta',       '45',     'Dias antes da data de entrega para pedido programado entrar na meta',                   'numero'),
  ('tolerancia_vinculacao', '10',     'Tolerância percentual de valor na vinculação automática pedido x PDF',                  'numero'),
  ('score_minimo_match',    '85',     'Score mínimo de similaridade de nome para vinculação automática (0-100)',               'numero'),
  ('reserva_meta',          '100318.67', 'Saldo atual da reserva de meta em R$',                                                'numero')
ON CONFLICT (chave) DO NOTHING;
