# Hyperparameter Best Selection Analysis

## Goal

Define a reliable method to identify the **best hyperparameter values** based on historical experiment data. The system should help users understand which parameter combinations are most likely to produce optimal model performance (measured by Recall@100).

## Current Implementation

The current "Hyperparameter Insights" section analyzes completed experiments by:

1. **Grouping** experiments by each hyperparameter value
2. **Calculating** average Recall@100 for each group
3. **Sorting** by average recall (descending)
4. **Displaying** the top value as "best" for each parameter

### Example Output
```
LEARNING RATE          BATCH SIZE           EPOCHS
0.005    0.085 (2)     1024    0.070 (1)    1      0.051 (1)
0.01     0.067 (4)     4096    0.038 (6)    50     0.039 (11)
0.05     0.055 (1)     2048    0.032 (9)    25     0.026 (4)
```

## Problems with Current Approach

### 1. Low Sample Size Dominance
Single experiments with lucky results can rank as "best" despite insufficient evidence:
- Batch size 1024 with **1 experiment** (0.070) beats 2048 with **9 experiments** (0.032)
- Epochs=1 shows as "best" with only **1 experiment** - clearly not a valid training configuration

### 2. No Uncertainty Consideration
The system treats 1 experiment the same as 15 experiments. There's no confidence measure or variance consideration.

### 3. Independent Parameter Analysis
Parameters are analyzed in isolation, ignoring potential interactions:
- LR=0.005 might only work well with batch_size=4096
- Current system can't capture these dependencies

### 4. Outlier Sensitivity
One outlier experiment can skew the average significantly, especially with small sample sizes.

## Possible Solutions

### Option 1: Bayesian Averaging (Shrinkage)

**Concept**: Apply a formula that pulls low-sample results toward the global mean.

**Formula**:
```
adjusted_score = (n × avg + k × global_avg) / (n + k)
```

Where:
- `n` = number of experiments with this parameter value
- `avg` = average recall for this parameter value
- `k` = prior strength (typically 3-5)
- `global_avg` = average recall across all experiments

**Pros**:
- Simple to implement
- Naturally handles uncertainty
- With 1 experiment, score regresses toward mean
- With many experiments, trusts the actual data

**Cons**:
- Requires tuning of `k` parameter
- Doesn't capture parameter interactions

### Option 2: Lower Confidence Bound (LCB)

**Concept**: Rank by a pessimistic estimate that penalizes variance and low sample sizes.

**Formula**:
```
score = avg - (std / sqrt(n))
```

Or with a tunable confidence parameter:
```
score = avg - z × (std / sqrt(n))
```

**Pros**:
- Rewards consistency over lucky single runs
- Naturally penalizes low sample sizes
- Based on sound statistical principles

**Cons**:
- Requires at least 2 experiments to calculate std
- Can be overly pessimistic with high variance

### Option 3: Minimum Sample Threshold

**Concept**: Don't rank parameters with fewer than N experiments (e.g., n < 3).

**Implementation**:
- Parameters with sufficient data: ranked normally
- Parameters with insufficient data: shown separately as "insufficient data" or grayed out

**Pros**:
- Very simple to implement
- Eliminates the most egregious false positives
- Easy to understand

**Cons**:
- Arbitrary threshold choice
- Loses information from low-sample parameters
- Doesn't solve the problem for parameters just above threshold

### Option 4: TPE-Inspired Probability Ratio

**Concept**: Based on Tree-structured Parzen Estimator, calculate the probability that a parameter value leads to "good" vs "bad" outcomes.

**Implementation**:
1. Define "good" experiments (e.g., top 25% by recall)
2. Define "bad" experiments (bottom 75%)
3. For each parameter value, calculate:
   ```
   score = P(good | param_value) / P(bad | param_value)
   ```
4. Higher ratio = parameter more associated with good outcomes

**Pros**:
- Naturally handles sample size through probability estimation
- Based on proven HPO methodology
- More robust to outliers

**Cons**:
- More complex to implement
- Threshold for "good" vs "bad" is arbitrary
- May need smoothing for low-sample categories

### Option 5: Best Combination Analysis

**Concept**: Instead of analyzing parameters independently, find which **combinations** appear in top experiments.

**Implementation**:
1. Identify top N experiments by recall
2. Find common parameter patterns across top experiments
3. Display as: "Top 5 experiments used: LR=0.005, batch=4096, epochs=50"

**Pros**:
- Captures parameter interactions
- Directly shows what worked
- Easy to interpret

**Cons**:
- Doesn't generalize to unseen combinations
- May overfit to specific experiments
- Less useful with diverse top experiments

## Recommended Approach

### Short-term (Quick Win)
Implement **Option 1 (Bayesian Averaging)** combined with **Option 3 (Minimum Threshold)**:

1. Apply Bayesian shrinkage with k=3:
   ```
   adjusted_score = (n × avg + 3 × global_avg) / (n + 3)
   ```

2. Gray out or mark parameters with n < 3 as "low confidence"

3. Display both the adjusted score and the sample count

This approach:
- Immediately fixes the misleading single-experiment rankings
- Is simple to implement and understand
- Provides a foundation for more sophisticated methods

### Medium-term (Enhanced Analysis)
Add **Option 5 (Best Combination Analysis)** as a separate section:

- Show the parameter combinations from top 5 experiments
- Highlight parameters that consistently appear in top results
- This complements the per-parameter analysis with interaction insights

### Long-term (Advanced)
Consider **Option 4 (TPE-Inspired)** for more sophisticated analysis:

- Implement probability-based scoring
- Add parameter importance ranking
- Potentially integrate with Optuna for active experiment suggestions

## Next Steps

1. **Implement Bayesian Averaging**: Update the `hyperparameter_analysis` API endpoint to use adjusted scores
2. **Add Confidence Indicators**: Show visual indicators for low-sample parameters
3. **Update UI**: Display adjusted scores with sample counts and confidence levels
4. **Add Combination Analysis**: New section showing top experiment parameter patterns
5. **Testing**: Validate that new rankings better reflect true best parameters
6. **Documentation**: Update user-facing docs explaining the methodology

## References

- [Bayesian Averaging / Shrinkage Estimators](https://en.wikipedia.org/wiki/Shrinkage_estimator)
- [TPE - Tree-structured Parzen Estimator](https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html)
- [Upper/Lower Confidence Bounds in Bandits](https://en.wikipedia.org/wiki/Multi-armed_bandit)
