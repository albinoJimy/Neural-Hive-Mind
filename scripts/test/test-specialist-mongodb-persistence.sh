#!/bin/bash

# Test MongoDB persistence of specialist opinions
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Testing Specialist MongoDB Persistence${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
MONGODB_NAMESPACE="mongodb-cluster"
DATABASE_NAME="neural_hive"
COLLECTION_NAME="specialist_opinions"

# Get MongoDB pod
echo -e "${YELLOW}Finding MongoDB pod...${NC}"
MONGO_POD=$(kubectl get pods -n "$MONGODB_NAMESPACE" -l app=mongodb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [ -z "$MONGO_POD" ]; then
  echo -e "${RED}✗ MongoDB pod not found in namespace: $MONGODB_NAMESPACE${NC}"
  echo ""
  echo -e "${YELLOW}Available pods:${NC}"
  kubectl get pods -n "$MONGODB_NAMESPACE"
  exit 1
fi

echo -e "${GREEN}✓ Found MongoDB pod: $MONGO_POD${NC}"
echo ""

# Test 1: Verify database and collection
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 1: Database and Collection${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Checking database and collection...${NC}"
COLLECTIONS=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "use $DATABASE_NAME; db.getCollectionNames();" 2>&1)

if echo "$COLLECTIONS" | grep -q "$COLLECTION_NAME"; then
  echo -e "${GREEN}✓ Collection '$COLLECTION_NAME' exists${NC}"
else
  echo -e "${YELLOW}⚠ Collection '$COLLECTION_NAME' not found${NC}"
  echo ""
  echo -e "${YELLOW}Available collections:${NC}"
  echo "$COLLECTIONS"
fi

echo ""

# Test 2: Count total opinions
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 2: Total Opinion Count${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Counting total opinions...${NC}"
TOTAL_COUNT=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "use $DATABASE_NAME; db.$COLLECTION_NAME.countDocuments({});" 2>&1 | tail -1)

echo -e "${GREEN}Total opinions: $TOTAL_COUNT${NC}"
echo ""

# Test 3: Opinions per specialist
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 3: Opinions by Specialist Type${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Aggregating opinions by specialist type...${NC}"
SPECIALIST_STATS=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "
    use $DATABASE_NAME;
    db.$COLLECTION_NAME.aggregate([
      {\$group: {_id: '\$specialist_type', count: {\$sum: 1}}},
      {\$sort: {_id: 1}}
    ]);
  " 2>&1)

echo ""
echo -e "${YELLOW}Opinions per specialist:${NC}"
echo "$SPECIALIST_STATS" | grep -E "(_id|count)" | while read -r line; do
  echo "  $line"
done

echo ""

# Test 4: Recent opinions
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 4: Recent Opinions (Sample)${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Fetching most recent opinion...${NC}"
RECENT_OPINION=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "
    use $DATABASE_NAME;
    db.$COLLECTION_NAME.find().sort({created_at: -1}).limit(1).pretty();
  " 2>&1)

if [ -n "$RECENT_OPINION" ]; then
  echo ""
  echo -e "${YELLOW}Most recent opinion:${NC}"
  echo "$RECENT_OPINION"
  echo ""

  # Validate opinion structure
  echo -e "${YELLOW}Validating opinion structure...${NC}"
  REQUIRED_FIELDS=(
    "opinion_id"
    "specialist_type"
    "plan_id"
    "intent_id"
    "confidence_score"
    "risk_score"
    "recommendation"
    "created_at"
  )

  for field in "${REQUIRED_FIELDS[@]}"; do
    if echo "$RECENT_OPINION" | grep -q "$field"; then
      echo -e "  ${GREEN}✓${NC} $field"
    else
      echo -e "  ${RED}✗${NC} $field (missing)"
    fi
  done
else
  echo -e "${YELLOW}⚠ No opinions found in collection${NC}"
fi

echo ""

# Test 5: Validate indexes
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 5: Collection Indexes${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Checking indexes...${NC}"
INDEXES=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "
    use $DATABASE_NAME;
    db.$COLLECTION_NAME.getIndexes();
  " 2>&1)

echo ""
echo -e "${YELLOW}Indexes found:${NC}"
echo "$INDEXES" | grep -E "(name|key)" | while read -r line; do
  echo "  $line"
done

# Check for recommended indexes
RECOMMENDED_INDEXES=(
  "plan_id"
  "intent_id"
  "specialist_type"
  "created_at"
)

echo ""
echo -e "${YELLOW}Recommended indexes:${NC}"
for index_field in "${RECOMMENDED_INDEXES[@]}"; do
  if echo "$INDEXES" | grep -q "$index_field"; then
    echo -e "  ${GREEN}✓${NC} $index_field"
  else
    echo -e "  ${YELLOW}⚠${NC} $index_field (not found)"
  fi
done

echo ""

# Test 6: Opinion quality metrics
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 6: Opinion Quality Metrics${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "${YELLOW}Calculating average confidence and risk scores...${NC}"
METRICS=$(kubectl exec -n "$MONGODB_NAMESPACE" "$MONGO_POD" -- \
  mongosh --quiet --eval "
    use $DATABASE_NAME;
    db.$COLLECTION_NAME.aggregate([
      {
        \$group: {
          _id: null,
          avg_confidence: {\$avg: '\$confidence_score'},
          avg_risk: {\$avg: '\$risk_score'},
          min_confidence: {\$min: '\$confidence_score'},
          max_confidence: {\$max: '\$confidence_score'},
          min_risk: {\$min: '\$risk_score'},
          max_risk: {\$max: '\$risk_score'}
        }
      }
    ]);
  " 2>&1)

echo ""
echo -e "${YELLOW}Quality Metrics:${NC}"
echo "$METRICS" | grep -E "(avg_|min_|max_)" | while read -r line; do
  echo "  $line"
done

echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Persistence Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ "$TOTAL_COUNT" -gt 0 ]; then
  echo -e "${GREEN}✓ MongoDB persistence is working${NC}"
  echo -e "  Total opinions stored: $TOTAL_COUNT"
  echo -e "  Collection: $DATABASE_NAME.$COLLECTION_NAME"
  echo ""
  echo -e "${YELLOW}Next steps:${NC}"
  echo "  - Review opinion quality metrics above"
  echo "  - Ensure all 5 specialists are persisting opinions"
  echo "  - Verify indexes are optimized for queries"
else
  echo -e "${YELLOW}⚠ No opinions found in MongoDB${NC}"
  echo ""
  echo -e "${YELLOW}Possible causes:${NC}"
  echo "  - Specialists not deployed yet"
  echo "  - No plans have been evaluated"
  echo "  - Connection issues between specialists and MongoDB"
  echo ""
  echo -e "${YELLOW}Troubleshooting:${NC}"
  echo "  1. Check specialist pods: kubectl get pods -A | grep specialist"
  echo "  2. Check specialist logs: kubectl logs -n specialist-business -l app.kubernetes.io/name=specialist-business"
  echo "  3. Test specialist connectivity: kubectl exec -n specialist-business deployment/specialist-business -- nc -zv mongodb.mongodb-cluster.svc.cluster.local 27017"
  echo "  4. Run integration test: ./scripts/test/test-specialists-integration.sh"
fi

echo ""
