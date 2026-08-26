# Qdrant Migration Deployment Checklist

## Pre-Deployment Checklist

### System Requirements
- [ ] **Python 3.12+** installed
- [ ] **Minimum 4GB RAM** (8GB recommended)
- [ ] **Minimum 10GB free disk space**
- [ ] **Docker** installed (for Qdrant container)
- [ ] **Git** installed for version control

### Environment Setup
- [ ] **Backup existing system**
  - [ ] Create full backup of `bot_data/` directory
  - [ ] Export current configuration files
  - [ ] Document current system state
  - [ ] Verify backup integrity

- [ ] **Update dependencies**
  - [ ] Install new Python packages from `requirements.txt`
  - [ ] Verify all dependencies are compatible
  - [ ] Test imports in Python environment

- [ ] **Configuration files**
  - [ ] Update `.env` file with Qdrant settings
  - [ ] Verify `qdrant_config.json` settings
  - [ ] Update `pyproject.toml` with new dependencies
  - [ ] Test configuration file syntax

### Data Migration
- [ ] **Stop all services**
  - [ ] Stop Discord bot
  - [ ] Stop web server/control panel
  - [ ] Stop any background processes

- [ ] **Data preparation**
  - [ ] Archive existing `bot_data/` (Qdrant storage + SQLite) — there is no ChromaDB anymore
  - [ ] Export user profiles and relationships
  - [ ] Document data schema differences
  - [ ] Prepare for fresh Qdrant instance

## Deployment Checklist

### Phase 1: Qdrant Setup
- [ ] **Start Qdrant service**
  - [ ] Launch Qdrant Docker container
  - [ ] Verify Qdrant is running on port 6333
  - [ ] Test Qdrant API connectivity
  - [ ] Check Qdrant cluster health

- [ ] **Initialize Qdrant Memory System**
  - [ ] Create `qdrant_memory_system.py` instance
  - [ ] Test basic Qdrant operations
  - [ ] Verify collection creation
  - [ ] Test embedding model loading

### Phase 2: Bot Integration
- [ ] **Update Discord bot**
  - [ ] Verify `discord_bot.py` entry path (loads config/state, injects via `serin/d1_1_serin_di.py`)
  - [ ] Verify message-manager wiring (`d4_4_core_manager.EnhancedMessageManagerV3`)
  - [ ] Test memory system initialization (`d2_2_core_memory/d3_4_memory_store.QdrantMemorySystem`)
  - [ ] Verify bot startup with Qdrant

- [ ] **Test basic functionality**
  - [ ] Test user profile creation
  - [ ] Test memory addition
  - [ ] Test basic search operations
  - [ ] Verify error handling

### Phase 3: Web API Integration
- [ ] **Verify control panel**
  - [ ] Panel is served in-process by uvicorn (`d3_3_panel_lifecycle.py`, default port 8081)
  - [ ] Test panel endpoints
  - [ ] Verify memory search functionality
  - [ ] Test user management endpoints

- [ ] **API testing** (panel default port: `CONTROL_PANEL_PORT=8081`)
  - [ ] Test `/api/status` endpoint
  - [ ] Test `/api/stats` endpoint
  - [ ] Test `/api/health` endpoint

### Phase 4: Performance Testing
- [ ] **Load testing**
  - [ ] Test memory ingestion rate (>1000 memories/minute)
  - [ ] Test search performance (<100ms average)
  - [ ] Test concurrent user operations
  - [ ] Monitor memory usage

- [ ] **Stress testing**
  - [ ] Test with large datasets
  - [ ] Test memory cleanup operations
  - [ ] Test error recovery
  - [ ] Monitor system stability

## Post-Deployment Checklist

### Verification Testing
- [ ] **Functional verification**
  - [ ] Test all Discord bot commands
  - [ ] Test memory search accuracy
  - [ ] Test user profile management
  - [ ] Test control panel functionality

- [ ] **Performance verification**
  - [ ] Measure search response times
  - [ ] Monitor memory usage patterns
  - [ ] Check Qdrant performance metrics
  - [ ] Verify system stability

### Monitoring Setup
- [ ] **Logging configuration**
  - [ ] Enable detailed Qdrant logging
  - [ ] Set up performance monitoring
  - [ ] Configure error alerts
  - [ ] Test log rotation

- [ ] **Health checks**
  - [ ] Configure automated health checks
  - [ ] Set up Qdrant monitoring
  - [ ] Configure memory usage alerts
  - [ ] Test alert notifications

### Documentation
- [ ] **Update documentation**
  - [ ] Update user guides with Qdrant features
  - [ ] Document new API endpoints
  - [ ] Create troubleshooting guide
  - [ ] Update deployment procedures

## Rollback Plan

### Immediate Rollback Steps
1. **Stop Qdrant services**
   - [ ] Stop Discord bot
   - [ ] Stop control panel
   - [ ] Stop Qdrant container

2. **Restore backup**
   - [ ] Restore Qdrant storage from backup
   - [ ] Restore SQLite database
   - [ ] Restore configuration files

3. **Restart services**
   - [ ] Start Discord bot with Qdrant (control panel starts in-process)
   - [ ] Verify functionality

### Rollback Triggers
- [ ] Search performance > 500ms average
- [ ] Memory system crashes > 3 times in 24 hours
- [ ] Data corruption detected
- [ ] User reports functionality loss
- [ ] System resource exhaustion

## Success Criteria

### Technical Metrics
- [ ] **Search Performance**: <100ms average query response time
- [ ] **Ingestion Rate**: >1000 memories/minute
- [ ] **Memory Efficiency**: <16GB RAM for 1M vectors
- [ ] **Availability**: 99.9% uptime
- [ ] **Data Integrity**: Zero data loss during migration

### Functional Requirements
- [ ] **Data Continuity**: All existing Qdrant/SQLite data preserved (there is no ChromaDB fallback)
- [ ] **Search Quality**: Hybrid search improves relevance by 20%+
- [ ] **Scalability**: Support 10M+ memories without performance degradation
- [ ] **Reliability**: Automatic recovery from failures
- [ ] **Maintainability**: Clear monitoring and debugging capabilities

### User Acceptance
- [ ] **Bot Functionality**: All Discord bot features work correctly
- [ ] **Control Panel**: All web interface functions properly
- [ ] **Search Results**: Memory search returns relevant results
- [ **Performance**: System response times acceptable to users
- [ ] **Stability**: No crashes or data loss during normal operation

## Final Verification

### System Health Check
- [ ] All services running without errors
- [ ] Qdrant cluster status: green
- [ ] Memory system statistics within expected ranges
- [ ] No error logs in monitoring system
- [ ] All automated tests passing

### User Acceptance Testing
- [ ] Test with real Discord users
- [ ] Collect feedback on search quality
- [ ] Monitor user-reported issues
- [ ] Verify performance under load
- [ ] Confirm feature completeness

### Documentation Review
- [ ] All documentation updated and accurate
- [ ] Deployment procedures documented
- [ ] Troubleshooting guide available
- [ ] API documentation complete
- [ ] User guides updated

## Deployment Sign-off

### Technical Team
- [ ] Lead Developer: _________________________
- [ ] DevOps Engineer: _________________________
- [ ] QA Engineer: _________________________
- [ ] System Architect: _________________________

### Stakeholders
- [ ] Product Manager: _________________________
- [ ] Project Manager: _________________________
- [ ] Client Representative: _________________________

### Deployment Summary
- **Deployment Date**: _________________________
- **Deployment Time**: _________________________
- **Duration**: _________________________
- **Issues Encountered**: _________________________
- **Rollback Required**: Yes / No
- **Post-Deployment Actions**: _________________________

---

**Note**: This checklist should be completed in order. Each phase must be fully verified before proceeding to the next. Any issues found should be documented and resolved before continuing.