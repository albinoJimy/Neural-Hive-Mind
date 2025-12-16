# Critérios de Promoção de Modelos ML

## DurationPredictor (ticket-duration-predictor)
- **Métrica**: MAE (Mean Absolute Error) em milissegundos
- **Threshold**: MAE < 15% da média de duração dos tickets
- **Cálculo**: `mae_percentage = (mae / mean_duration) * 100`
- **Exemplo**: Se média de duração = 60000ms, MAE deve ser < 9000ms (15%)
- **Promoção**: Automática se `mae_percentage < 15.0`

## AnomalyDetector (ticket-anomaly-detector)
- **Métrica**: Precision (Precisão)
- **Threshold**: Precision > 0.75 (75%)
- **Cálculo**: `precision = TP / (TP + FP)`
- **Exemplo**: De 100 anomalias detectadas, 75+ devem ser verdadeiras
- **Promoção**: Automática se `precision > 0.75`

## LoadPredictor (load-predictor-*)
- **Métrica**: MAPE (Mean Absolute Percentage Error)
- **Threshold**: MAPE < 20% para cada horizonte (60m, 360m, 1440m)
- **Cálculo**: `mape = mean(|actual - predicted| / actual) * 100`
- **Promoção**: Automática se `mape < 20.0` para o horizonte específico

## Processo de Promoção
1. Modelo treinado é registrado no MLflow com stage `None`
2. `ModelRegistry.promote_model()` valida critérios
3. Se aprovado, transiciona para stage `Production`
4. Modelos antigos em `Production` são arquivados automaticamente
5. Cache de modelos é limpo para forçar reload
