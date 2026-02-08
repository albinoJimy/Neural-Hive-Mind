# Feature Engineering Results - 2026-02-08

## Summary of Experiments

### Dataset
- **Specialist**: Business
- **Total Feedbacks**: 479
- **Positive samples (approve)**: ~97 (20.3%)
- **Plans matched**: 89 out of 479 opinions

### Models Tested

| Version | Features | F1 | Precision | Recall | AUC-ROC | Notes |
|---------|----------|-----|-----------|--------|---------|-------|
| V1 | Base + human_rating | 1.000 | 1.000 | 1.000 | N/A | Data leakage |
| V2 | Base only | 0.000 | 0.000 | 0.000 | 0.552 | Cannot predict positive |
| V3 | Feature engineering (22 features) | 0.355 | 0.216 | 1.000 | 0.552 | Detects all approves but low precision |
| V4 | + Threshold optimization | 0.355 | 0.216 | 1.000 | 0.552 | Same as V3 |

### Key Findings

1. **Data Leakage in V1**: Feature `human_rating` (95.97% importance) comes from the feedback itself
2. **Base features insufficient**: confidence, risk, opinion_rec alone cannot predict approve
3. **Feature engineering helped**: F1 improved from 0.000 to 0.355
4. **AUC-ROC unchanged at 0.552**: Features have limited discriminative power

### Top Features (V3)

| Feature | Importance |
|---------|-------------|
| model_rec_reject | 20.77% |
| complexity_eval | 19.53% |
| model_rec_review | 19.02% |
| semantic_quality | 16.60% |
| confidence_score | 16.31% |

### Root Cause Analysis

The low AUC-ROC (0.552) suggests that:

1. **Synthetic feedback problem**: The "balanced" feedbacks we created are based on simple heuristics, not real human decisions
2. **Weak signal**: There's no strong pattern in the data that differentiates approve from reject
3. **Small dataset**: 97 positive samples is insufficient for complex patterns

### Available Data (Not Yet Used)

1. **Reasoning Factors** (with scores):
   - ml_confidence, ml_risk (3689 each)
   - semantic_quality_analysis (506)
   - complexity_evaluation (506)
   - semantic_architecture_analysis (506)
   - semantic_security_analysis (506)
   - kpi_alignment (81)

2. **Plan Features**:
   - complexity_score
   - estimated_duration_ms
   - original_domain (SECURITY, PERFORMANCE, FEATURE, BUGFIX)
   - original_priority (normal, high, critical)
   - tasks array with details

3. **Task-Level Features**:
   - task_type (create, update, delete, etc.)
   - required_capabilities
   - constraints (security_level, timeout)

### Recommendations

1. **Collect Real Human Feedback**
   - Use the web interface at http://37.60.241.150:30080
   - Target: 500+ real human decisions
   - Focus on edge cases (confusing examples)

2. **Add Domain-Specific Features**
   - For business specialist: ROI impact, strategic alignment
   - For technical specialist: tech debt impact, security implications
   - For behavior specialist: user experience impact

3. **Use Multi-Specialist Approach**
   - Train ensemble model combining all 5 specialists
   - Use correlation between specialist opinions

4. **Active Learning**
   - Identify uncertain predictions
   - Prioritize for human review
   - Iteratively improve model

5. **Consider Alternative Approaches**
   - Ranking approach instead of classification
   - Similarity-based recommendations
   - Rule-based system + ML hybrid

## MLflow Runs

| Run ID | Model | Purpose | Status |
|--------|-------|---------|--------|
| fa606c9601d641239886722087844472 | RF | With data leakage | Invalid |
| 8fca481c1b424230930336a1bb33cfa3 | GB | No feat eng, scaled | F1=0 |
| 99cd637e3ee84ae2a85838631faaa64a | RF | Feature engineering | F1=0.355 |
| f8221b4650864ff8959dd7642308aa3a | GB | + Threshold opt | F1=0.355 |

---

**Status**: Feature engineering improved results but AUC-ROC indicates fundamental signal weakness.
**Next Priority**: Collect real human feedback through web interface.
