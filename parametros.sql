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
  ('reserva_meta',             '100318.67', 'Saldo atual da reserva de meta em R$',                                                                  'numero'),
  ('tolerancia_entrada',       '0',         'Tolerância % na conferência de entradas (0 = deve bater exato)',                                       'numero'),
  ('tolerancia_saida_cima_a',  '0',         'Tolerância % para cima na saída — Tabela A',                                                          'numero'),
  ('tolerancia_saida_cima_b',  '0',         'Tolerância % para cima na saída — Tabela B',                                                          'numero'),
  ('tolerancia_saida_cima_c',  '0',         'Tolerância % para cima na saída — Tabela C',                                                          'numero'),
  ('tolerancia_saida_cima_d',  '8',         'Tolerância % para cima na saída — Tabela D',                                                          'numero'),
  ('tolerancia_saida_cima_e',  '0',         'Tolerância % para cima na saída — Tabela E',                                                          'numero'),
  ('tolerancia_saida_cima_f',  '8',         'Tolerância % para cima na saída — Tabela F',                                                          'numero'),
  ('tolerancia_saida_baixo',   '0',         'Tolerância % para baixo na saída — todas as tabelas (0 = nunca aceita menos)',                        'numero')
ON CONFLICT (chave) DO NOTHING;
