# Diretrizes e Regras do Repositório (Agenda Aeronautas)

## Regras de Negócio para Cálculos

### Horário Noturno para Aeronautas LATAM
- **Regra**: Para aeronautas da **LATAM**, o ACT (Acordo Coletivo de Trabalho) atual prevê que o pagamento de noturno seja calculado apenas entre **22:00 e 04:59** (inclusive).
- **Escopo**: Esta regra se aplica **exclusivamente** para o cálculo do **Tempo em Solo (entre etapas)**.
- **Identificação**: A LATAM deve ser identificada no nome do arquivo PDF fonte (ou no arquivo CSV correspondente gerado a partir dele, geralmente contendo a substring "LATAM" no nome do arquivo).
- **Diferenciação**: Para as demais companhias aéreas (como Azul, CIV, etc.), mantém-se o cálculo padrão de pagamento noturno (geralmente das 21:00 às 09:00, ou conforme as respectivas convenções).
- **Impacto nos Códigos**: Ao analisar ou editar scripts que calculam o tempo noturno (especialmente `CRIA VALORES FINAIS TEMPO SOLO.py`), deve-se parametrizar o período noturno (de pagamento e especial) para o Tempo Solo com base na identificação da LATAM no arquivo sendo processado. Para os outros cálculos (como jornada, operação, etc.), as regras gerais não mudam.

