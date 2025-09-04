# Webhook System Improvements

This document outlines the comprehensive webhook system enhancements implemented in `app/webhook.py`.

## ✅ Implemented Features

### 1. Stability - Retry Mechanism
```python
async def send_with_retry(payload: dict, max_attempts: int = 3) -> bool:
    """
    Advanced retry mechanism with:
    - Exponential backoff (1, 2, 4 seconds)
    - Payload validation before each attempt
    - Smart error handling (no retry for 4xx errors)
    - Increased timeout for each retry attempt
    """
```

**Key Features:**
- **Exponential backoff**: 1, 2, 4 second delays between attempts
- **Dynamic retry counts**: Hot leads (5), Calculated (3), Cold (2) attempts
- **Smart error handling**: No retry for 400-499 client errors
- **Timeout scaling**: Increases timeout with each attempt
- **Comprehensive logging**: Detailed logs for debugging

### 2. Monitoring - WebhookMetrics Class
```python
class WebhookMetrics:
    """Complete monitoring solution for webhook health"""
    
    success_count = 0
    error_count = 0
    last_error_time: Optional[datetime] = None
    last_error_message: Optional[str] = None
    
    @classmethod
    def get_health(cls) -> dict:
        """Returns comprehensive health statistics"""
```

**Metrics Tracked:**
- ✅ Success/Error counts
- ✅ Success rate calculation
- ✅ Last error timestamp and message
- ✅ Health status (healthy/degraded based on 80% success rate)
- ✅ Total request count

### 3. Payload Validation
```python
def validate_payload(payload: dict, lead_type: str) -> bool:
    """
    Comprehensive payload validation:
    - Required fields check
    - Lead type validation
    - User ID format validation
    - Special validations per lead type
    """
```

**Validation Rules:**
- ✅ Required fields: `['user_id', 'lead_type', 'timestamp']`
- ✅ Lead type validation: `['hot', 'cold', 'calculated']`
- ✅ User ID format checking
- ✅ Special validation for hot leads (priority check)
- ✅ Raises `ValueError` for invalid data

### 4. Enhanced Testing
```python
async def test_webhook_connection() -> dict:
    """
    Comprehensive webhook testing with:
    - Connection testing
    - Response time measurement
    - Health metrics integration
    - Detailed error reporting
    """
```

## 🚀 Production Recommendations

### 1. Persistent Timers with Redis

For production deployment, implement Redis-based timer persistence:

```python
# Redis implementation example
import redis
import json
from datetime import datetime, timedelta

class PersistentTimerService:
    def __init__(self):
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=os.getenv('REDIS_PORT', 6379),
            db=os.getenv('REDIS_DB', 0),
            decode_responses=True
        )
    
    async def start_calculated_timer(self, user_id: int, delay_minutes: int = 60):
        """Start persistent timer that survives restarts"""
        
        # Calculate execution time
        execute_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        
        # Store timer data in Redis
        timer_data = {
            'user_id': user_id,
            'timer_type': 'calculated_lead',
            'execute_at': execute_at.isoformat(),
            'delay_minutes': delay_minutes,
            'created_at': datetime.utcnow().isoformat()
        }
        
        # Set with TTL slightly longer than delay
        ttl_seconds = (delay_minutes * 60) + 300  # +5 min buffer
        
        self.redis_client.setex(
            f"timer:calculated:{user_id}",
            ttl_seconds,
            json.dumps(timer_data)
        )
        
        # Schedule background task
        await self._schedule_timer_execution(user_id, delay_minutes * 60)
    
    async def restore_timers_on_startup(self):
        """Restore active timers after restart"""
        pattern = "timer:calculated:*"
        
        for key in self.redis_client.scan_iter(match=pattern):
            try:
                timer_data = json.loads(self.redis_client.get(key))
                user_id = timer_data['user_id']
                execute_at = datetime.fromisoformat(timer_data['execute_at'])
                
                # Check if timer should still execute
                now = datetime.utcnow()
                if execute_at > now:
                    # Reschedule remaining time
                    remaining_seconds = int((execute_at - now).total_seconds())
                    await self._schedule_timer_execution(user_id, remaining_seconds)
                else:
                    # Timer expired during downtime - execute immediately
                    await self._execute_calculated_timer(user_id)
                    self.redis_client.delete(key)
                    
            except Exception as e:
                logger.error(f"Error restoring timer {key}: {e}")
                self.redis_client.delete(key)
```

### 2. Advanced Monitoring Integration

```python
# Prometheus metrics example
from prometheus_client import Counter, Histogram, Gauge

class PrometheusMetrics:
    webhook_requests_total = Counter(
        'webhook_requests_total',
        'Total webhook requests',
        ['lead_type', 'status']
    )
    
    webhook_response_time = Histogram(
        'webhook_response_time_seconds',
        'Webhook response time',
        ['lead_type']
    )
    
    webhook_active_timers = Gauge(
        'webhook_active_timers',
        'Number of active timers'
    )
```

### 3. Error Recovery Strategies

```python
class ErrorRecoveryService:
    @staticmethod
    async def handle_critical_lead_failure(user_data: dict, lead_type: str):
        """Handle critical lead delivery failures"""
        
        if lead_type == 'hot':
            # Store in dead letter queue for manual processing
            await DeadLetterQueue.store_failed_lead(user_data, lead_type)
            
            # Send alert to admin
            await AlertService.send_critical_alert(
                f"Critical hot lead failed: {user_data.get('tg_id')}"
            )
            
        elif lead_type == 'calculated':
            # Retry later with longer delay
            await TimerService.start_calculated_timer(
                user_data.get('tg_id'), 
                delay_minutes=120  # 2 hours
            )
```

## 📊 Health Monitoring

### Current Health Check Endpoint
```python
# Usage in web admin or health check endpoint
health_data = WebhookService.get_webhook_health()

{
    "total_requests": 150,
    "success_count": 145,
    "error_count": 5,
    "success_rate": 0.967,
    "last_error_time": "2024-01-15T10:30:00Z",
    "last_error_message": "HTTP 503: Service Temporarily Unavailable",
    "status": "healthy"  // or "degraded"
}
```

### Recommended Alerting Rules
- 🚨 **Critical**: Success rate < 80%
- ⚠️ **Warning**: Success rate < 90%
- 📊 **Info**: Error count > 10 in last hour
- 🔄 **Recovery**: Success rate back > 95%

## 🛡️ Security Considerations

### 1. Webhook URL Protection
```python
# Add authentication headers if n8n supports it
headers = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {os.getenv("N8N_API_KEY")}',
    'X-API-Key': os.getenv("WEBHOOK_SECRET_KEY")
}
```

### 2. Payload Encryption (Optional)
```python
import cryptography.fernet

def encrypt_sensitive_data(payload: dict) -> dict:
    """Encrypt sensitive fields before sending"""
    sensitive_fields = ['first_name', 'username']
    
    cipher = Fernet(os.getenv('WEBHOOK_ENCRYPTION_KEY'))
    
    for field in sensitive_fields:
        if field in payload and payload[field]:
            payload[field] = cipher.encrypt(
                payload[field].encode()
            ).decode()
    
    return payload
```

## 🔧 Configuration

### Environment Variables
```bash
# Required
N8N_WEBHOOK_URL=https://your-n8n-instance.com/webhook/fitness-bot-leads

# Optional Security
N8N_API_KEY=your_api_key_here
WEBHOOK_SECRET_KEY=your_secret_key_here
WEBHOOK_ENCRYPTION_KEY=your_fernet_key_here

# Redis for Persistent Timers (Production)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Monitoring
WEBHOOK_METRICS_ENABLED=true
PROMETHEUS_METRICS_PORT=9090
```

## 📈 Performance Optimization

### 1. Connection Pooling
```python
# Use persistent connection pool
connector = aiohttp.TCPConnector(
    limit=100,  # Total connection pool size
    limit_per_host=30,  # Per host limit
    keepalive_timeout=30,
    enable_cleanup_closed=True
)

session = aiohttp.ClientSession(connector=connector)
```

### 2. Batch Processing for High Volume
```python
async def send_batch_leads(leads_batch: List[dict], batch_size: int = 10):
    """Send multiple leads in parallel batches"""
    
    for i in range(0, len(leads_batch), batch_size):
        batch = leads_batch[i:i + batch_size]
        
        # Send batch in parallel
        tasks = [
            WebhookService.send_lead_to_n8n(lead['user_data'], lead['type'])
            for lead in batch
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle failures
        for result, lead in zip(results, batch):
            if isinstance(result, Exception):
                await ErrorRecoveryService.handle_critical_lead_failure(
                    lead['user_data'], lead['type']
                )
```

## 🎯 Current Implementation Status

✅ **Completed Features:**
- Retry mechanism with exponential backoff
- Comprehensive metrics and health monitoring  
- Payload validation with detailed error messages
- Advanced testing utilities
- Smart error handling and logging
- Dynamic retry counts based on lead criticality

🔄 **Recommended Next Steps:**
1. Implement Redis-based persistent timers for production
2. Add Prometheus metrics integration
3. Set up monitoring alerts and dashboards
4. Implement dead letter queue for critical failures
5. Add webhook authentication and encryption
6. Create automated testing suite for webhook reliability

The current webhook system provides a solid foundation with enterprise-grade reliability features. The persistent timer implementation with Redis should be the next priority for production deployment.