#!/usr/bin/env python3
"""
Script to approve a cognitive plan directly via MongoDB and Kafka.
Bypasses the approval service REST API for testing purposes.
Run from within the neural-hive namespace.
"""

import json
import os
from datetime import datetime

import pymongo
from confluent_kafka import Producer


PLAN_ID = os.getenv('PLAN_ID', '60fa055d-b9a7-4082-b54f-068b436d077a')
INTENT_ID = os.getenv('INTENT_ID', '63ca4c0a-4f31-4515-ac20-c5a1bb094905')
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'neural-hive-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092')
KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'cognitive-plans-approval-responses')


def get_mongo_client():
    return pymongo.MongoClient('mongodb://root:local_dev_password@mongodb.mongodb-cluster.svc.cluster.local:27017')


def get_kafka_producer():
    config = {
        'bootstrap.servers': KAFKA_BOOTSTRAP_SERVERS,
        'client.id': 'approval-test-script',
        'acks': 'all',
    }
    return Producer(config)


def update_approval_in_mongodb(client, plan_id: str) -> dict:
    db = client['neural_hive']
    collection = db['plan_approvals']

    approval = collection.find_one({'plan_id': plan_id})

    if approval:
        print(f"Found existing approval for plan {plan_id}")
        print(f"  Current status: {approval.get('status', 'unknown')}")

        update_result = collection.update_one(
            {'plan_id': plan_id},
            {
                '$set': {
                    'status': 'approved',
                    'decision': 'approved',
                    'approved_by': 'test-admin',
                    'approved_at': datetime.utcnow(),
                    'comments': 'Aprovado via script de teste - Fluxo C completamento',
                }
            }
        )

        print(f"  Updated: {update_result.modified_count} document(s)")

        updated = collection.find_one({'plan_id': plan_id})
        return updated
    else:
        print(f"No approval found for plan {plan_id}")
        new_approval = {
            'approval_id': f'approval-{plan_id[:8]}',
            'plan_id': plan_id,
            'intent_id': INTENT_ID,
            'status': 'approved',
            'decision': 'approved',
            'requested_at': datetime.utcnow(),
            'approved_by': 'test-admin',
            'approved_at': datetime.utcnow(),
            'comments': 'Aprovado via script de teste - Fluxo C completamento',
            'risk_score': 0.41,
            'risk_band': 'medium',
            'is_destructive': False,
            'cognitive_plan': {
                'plan_id': plan_id,
                'intent_id': INTENT_ID,
                'tasks': []
            }
        }

        result = collection.insert_one(new_approval)
        print(f"  Created new approval: {result.inserted_id}")
        return new_approval


def publish_approval_to_kafka(producer, approval: dict):
    plan_id = approval['plan_id']
    intent_id = approval.get('intent_id', INTENT_ID)

    message = {
        'plan_id': plan_id,
        'intent_id': intent_id,
        'decision': 'approved',
        'approved_by': 'test-admin',
        'approved_at': datetime.utcnow().isoformat(),
        'comments': 'Aprovado via script de teste - Fluxo C completamento',
        'cognitive_plan': approval.get('cognitive_plan', {}),
        'timestamp': datetime.utcnow().isoformat(),
    }

    def delivery_callback(err, msg):
        if err:
            print(f'ERROR: Message delivery failed: {err}')
        else:
            print(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')

    producer.produce(
        KAFKA_TOPIC,
        key=plan_id.encode('utf-8'),
        value=json.dumps(message).encode('utf-8'),
        callback=delivery_callback
    )

    producer.flush()
    print(f"Published approval response to {KAFKA_TOPIC}")


def main():
    print("=" * 60)
    print("Plan Approval Script - Fluxo C Completion")
    print("=" * 60)
    print(f"Plan ID: {PLAN_ID}")
    print(f"Intent ID: {INTENT_ID}")
    print("=" * 60)

    print("\n[1/2] Connecting to MongoDB...")
    try:
        mongo_client = get_mongo_client()
        mongo_client.admin.command('ping')
        print("  Connected to MongoDB successfully")
    except Exception as e:
        print(f"  ERROR connecting to MongoDB: {e}")
        return 1

    print("\n[2/3] Updating approval in MongoDB...")
    try:
        approval = update_approval_in_mongodb(mongo_client, PLAN_ID)
        print(f"  Approval status: {approval['status']}")
    except Exception as e:
        print(f"  ERROR updating MongoDB: {e}")
        mongo_client.close()
        return 1

    print("\n[3/3] Publishing approval to Kafka...")
    try:
        kafka_producer = get_kafka_producer()
        publish_approval_to_kafka(kafka_producer, approval)
        print("  Approval published successfully")
    except Exception as e:
        print(f"  ERROR publishing to Kafka: {e}")
        mongo_client.close()
        return 1

    mongo_client.close()
    kafka_producer.close()

    print("\n" + "=" * 60)
    print("APPROVAL COMPLETE")
    print("=" * 60)
    print(f"Plan {PLAN_ID} has been approved.")
    print("=" * 60)

    return 0


if __name__ == '__main__':
    exit(main())
