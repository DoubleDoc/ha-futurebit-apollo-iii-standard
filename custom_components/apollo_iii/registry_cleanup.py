"""Prune obsolete integration-owned entities from v0.1/v0.2.

Only exact known unique IDs are removed. Recorder history is not purged.
"""
from homeassistant.helpers import entity_registry as er
from .sensor import SPECS

KEEP={s[0] for s in SPECS}|{'disk_0_percent','disk_1_percent','hashboard_energy','online','mode_select','mining_switch','set_minerHashrate','set_fanTemp','set_fanPwm','restart','start','stop','miner_error_incidents','miner_last_error','miner_last_error_time','miner_last_error_category','miner_fault'}
# Sensor keys from v0.1 and v0.2 that have been retired.
OLD={'asic_detection_failures','asic_failed_sessions','asic_detection_fault','last_asic_fault','last_asic_fault_time','miner_sessions_observed','miner_failed_sessions','controller_temp','miner_mode','miner_hashrate_target','fan_temp_target','fan_pwm_target',
     'hashrate_ghs','efficiency','chip_speed','miner_temp_mcu','miner_fan_mcu',
     'board_power_raw','board_current_raw','efficiency_raw','master_diff',
     'master_uptime','master_boards','master_spi_errors','master_osc',
     'miner_version','miner_temperature_min_raw','miner_temperature_avg_raw',
     'miner_temperature_max_raw','miner_temperature_count','pool_difficulty',
     'service_requested','miner_status','cpu_architecture','architecture',
     'disk_0_used','disk_0_total','disk_1_used','disk_1_total'}
for interval in ('int_0','int_30','int_300','int_900','int_3600'):
    for field in ('bySol','byDiff','byPool','byJobs','solutions','errors','errorRate','chipSpeed','chipRestarts'):
        OLD.add(f'{interval}_{field}')
for field in ('jobs','cleanFlags','sharesSent','sharesAccepted','sharesRejected',
              'solutionsAccepted','minRespTime','avgRespTime','maxRespTime',
              'shareLoss','poolTotal','inService','subscribeError','diffChanges',
              'reconnections','reconnectionsOnErrors','defaultJobShares',
              'staleJobShares','duplicateShares','lowDifficultyShares',
              'pwcSharesSent','pwcSharesDropped','bigDiffShares',
              'belowTargetShare','pwcRestart','statOverflow'):
    OLD.add(f'pool_{field}')
for field in ('revision','spiNum','spiLen','pwrNum','pwrLen','btcNum',
              'specVoltage','chips','pwrOn','pwrOnTarget','revAdc',
              'temperature','temperature1','ocp','heaterErr','heaterErrNum',
              'inOHOsc','ohOscNum','ohOscTime','overheats','overheatsTime',
              'lowCurrRst','brokenPwc','solutions','errors','ghs',
              'errorRate','chipRestarts','wattPerGHs','osc','oscStopChip'):
    OLD.add(f'slot0_{field}')
for i in range(8):
    OLD.add(f'fan_{i}_rpm')
    OLD.add(f'slot0_current_{i}')

async def async_cleanup(hass, entry):
    """Remove only known retired sensor entities owned by this config entry.

    Look up by config-entry ownership and exact unique ID rather than
    assuming a registry platform lookup will match every historical entry.
    Do not remove any recorder history or active miner online binary sensor.
    """
    registry = er.async_get(hass)
    retired_ids = {f"{entry.entry_id}_{key}" for key in OLD - KEEP}
    for entity in list(er.async_entries_for_config_entry(registry, entry.entry_id)):
        if (entity.domain in ('sensor', 'binary_sensor')
                and entity.platform == 'apollo_iii'
                and entity.unique_id in retired_ids):
            registry.async_remove(entity.entity_id)
