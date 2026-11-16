"""Verified Apollo III telemetry and energy estimate."""
from datetime import datetime, timedelta, timezone
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfTemperature, UnitOfPower, UnitOfElectricCurrent, UnitOfElectricPotential, PERCENTAGE
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util
from .const import DOMAIN
from .entity import ApolloEntity, miner_stats, is_set

def at(data, *path):
    for key in path:
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and isinstance(key, int) and 0 <= key < len(data):
            data = data[key]
        else:
            return None
    return data

MODE_LABELS = {'super_eco': 'Super ECO', 'eco': 'ECO', 'balanced': 'Balanced', 'turbo': 'Turbo'}

def hashrate_target(settings):
    """Describe the hashrate target the miner actually runs with.

    apolloapi-v2 (src/configurator.js) passes `-hashrate` only in custom mode
    with a set minerHashrate; otherwise the preset power mode applies and the
    stored minerHashrate is ignored. Custom without a hashrate falls back to eco.
    """
    mode = settings.get('minerMode')
    hashrate = settings.get('minerHashrate')
    if mode == 'custom':
        if is_set(hashrate):
            return f'Custom {int(float(hashrate))} TH/s'
        return 'ECO preset'
    if mode in MODE_LABELS:
        return f'{MODE_LABELS[mode]} preset'
    return None

# Preserve existing unique IDs for measurements that were already in v0.1.
# key, label, coordinator, path, scale, unit, device class, state class, diagnostic
SPECS = [
    ('cpu_temp','Controller temperature','mcu',('temperature',),0.001,'°C',SensorDeviceClass.TEMPERATURE,SensorStateClass.MEASUREMENT,False),
    ('cpu_used','CPU usage','mcu',('cpu','usedPercent'),1,'%',None,SensorStateClass.MEASUREMENT,False),
    ('cpu_threads','CPU threads','mcu',('cpu','threads'),1,None,None,None,True),
    ('memory_used','Memory used','mcu',('memory','used'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('memory_available','Memory available','mcu',('memory','available'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('memory_total','Memory total','mcu',('memory','total'),1/1024,'MiB',None,None,True),
    ('service_status','Miner service status','settings',('services',),1,None,None,None,False),
    ('board_watts','Hashboard power','miner',('master','boardsW'),1,'W',SensorDeviceClass.POWER,SensorStateClass.MEASUREMENT,False),
    ('board_amps','Hashboard current','miner',('master','boardsI'),1,'A',SensorDeviceClass.CURRENT,SensorStateClass.MEASUREMENT,False),
    ('hashrate_ths','Hashrate','miner',('slots','int_0','ghs'),0.001,'TH/s',None,SensorStateClass.MEASUREMENT,False),
    ('temperature_avg','Miner average temperature','miner',('temperature','avr'),1,'°C',SensorDeviceClass.TEMPERATURE,SensorStateClass.MEASUREMENT,False),
    ('temperature_max','Miner maximum temperature','miner',('temperature','max'),1,'°C',SensorDeviceClass.TEMPERATURE,SensorStateClass.MEASUREMENT,True),
    ('hashboard_temp','Hashboard temperature','miner',('slots','int_0','temperature1'),1,'°C',SensorDeviceClass.TEMPERATURE,SensorStateClass.MEASUREMENT,False),
    ('fan_speed','Miner fan speed','miner',('fans','int_0','rpm',0),1,'rpm',None,SensorStateClass.MEASUREMENT,False),
    # The slot-level errorRate/errors fields are always 0 on the Apollo III;
    # chip errors are reported in the master interval stats.
    ('hashboard_error_rate','Chip error rate (5 min)','miner',('master','intervals','int_300','errorRate'),1,'%',None,SensorStateClass.MEASUREMENT,False),
    ('efficiency_j_th','Mining efficiency','miner',('slots','int_0','wattPerGHs'),1000,'J/TH',None,SensorStateClass.MEASUREMENT,False),
    ('pool_accepted','Pool accepted shares','miner',('pool','intervals','int_0','sharesAccepted'),1,None,None,None,False),
    ('pool_rejected','Pool rejected shares','miner',('pool','intervals','int_0','sharesRejected'),1,None,None,None,False),
    ('pool_sent','Pool sent shares','miner',('pool','intervals','int_0','sharesSent'),1,None,None,None,True),
    ('solutions','Miner solutions','miner',('slots','int_0','solutions'),1,None,None,None,True),
    ('hardware_errors','Chip errors since miner start','miner',('master','intervals','int_0','errors'),1,None,None,SensorStateClass.TOTAL_INCREASING,True),
    ('hashrate_1h_ths','Hashrate (1 h average)','miner',('master','intervals','int_3600','bySol'),0.001,'TH/s',None,SensorStateClass.MEASUREMENT,False),
    ('spi_errors','Master SPI errors','miner',('master','errorSpi'),1,None,None,None,True),
    ('active_boards','Active hashboards','miner',('master','boards'),1,None,None,None,True),
    ('miner_uptime','Miner uptime','miner',('master','upTime'),1,'s',None,SensorStateClass.MEASUREMENT,True),
    ('pool_host','Pool host','miner',('pool','host'),1,None,None,None,True),
    ('root_disk_used','Root disk used','mcu',('disks',0,'used'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('root_disk_total','Root disk total','mcu',('disks',0,'total'),1/1024,'MiB',None,None,True),
    ('log_disk_used','Log disk used','mcu',('disks',1,'used'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('log_disk_total','Log disk total','mcu',('disks',1,'total'),1/1024,'MiB',None,None,True),
    ('controller_uptime_raw','Controller boot time','mcu',('uptime',),1,None,None,None,True),
    ('operating_system','Operating system','mcu',('operatingSystem',),1,None,None,None,True),
    ('load_average','Linux load average','mcu',('loadAverage',),1,None,None,None,True),
    ('memory_cache','Memory cache','mcu',('memory','cache'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('memory_swap','Memory swap','mcu',('memory','swap'),1/1024,'MiB',None,SensorStateClass.MEASUREMENT,True),
    ('target_hashrate_mode','Hashrate target setting','settings',('settings','minerHashrate'),1,None,None,None,False),
    ('fan_target_mode','Fan control setting','settings',('settings','fanPwm'),1,None,None,None,False),
]

class ApolloSensor(ApolloEntity, SensorEntity):
    def __init__(self, entry, coordinator, spec):
        key,name,group,path,scale,unit,device_class,state_class,diagnostic = spec
        super().__init__(entry,coordinator,key,name)
        self.group,self.path,self.scale = group,path,scale
        self._attr_native_unit_of_measurement=unit
        self._attr_device_class=device_class
        self._attr_state_class=state_class
        if diagnostic:
            self._attr_entity_category=EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        data=self.coordinator.data or {}
        if self.group == 'miner':
            data=miner_stats(data)
            if data is None:
                return None
        value=at(data,*self.path)
        if self._attr_unique_id.endswith('_target_hashrate_mode'):
            return hashrate_target(data.get('settings') or {})
        if self._attr_unique_id.endswith('_fan_target_mode'):
            settings = data.get('settings') or {}
            pwm = settings.get('fanPwm')
            temp = settings.get('fanTemp')
            # The miner backend ignores 0/empty values, as here.
            if is_set(pwm):
                return f'Fixed PWM {pwm}%'
            if is_set(temp):
                return f'Temperature target {temp} °C'
            return 'AUTO'
        if self.path == ('services',):
            value=next((v.get('status') for v in (value or []) if v.get('serviceName')=='miner'),None)
        if isinstance(value,(int,float)) and not isinstance(value,bool):
            return round(value*self.scale,4)
        return value

    @property
    def extra_state_attributes(self):
        if not self._attr_unique_id.endswith('_target_hashrate_mode'):
            return None
        settings = (self.coordinator.data or {}).get('settings') or {}
        return {
            'miner_mode': settings.get('minerMode'),
            # Used only when the mode is custom.
            'custom_hashrate_ths': settings.get('minerHashrate'),
        }

    @property
    def available(self):
        # Frozen miner stats would otherwise look like live readings.
        if self.group == 'miner' and (self.coordinator.data or {}).get('stale'):
            return False
        return super().available

class Efficiency1h(ApolloEntity, SensorEntity):
    """J/TH from current hashboard power over the 1 h average hashrate.

    Same formula as the Apollo dashboard (apolloui-v2 reselect/miner.js). The
    miner reports no 1 h average power, so power is the current reading.
    """
    _attr_native_unit_of_measurement='J/TH'
    _attr_state_class=SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision=2
    _attr_icon='mdi:lightning-bolt-outline'

    def __init__(self,entry,coordinator):
        super().__init__(entry,coordinator,'efficiency_1h_j_th','Mining efficiency (1 h average)')

    @property
    def available(self):
        return super().available and not (self.coordinator.data or {}).get('stale')

    @property
    def native_value(self):
        stats=miner_stats(self.coordinator.data)
        if not stats:
            return None
        power=at(stats,'master','boardsW')
        ghs=at(stats,'master','intervals','int_3600','bySol')
        if not isinstance(power,(int,float)) or not isinstance(ghs,(int,float)) or ghs <= 0:
            return None
        return round(power/ghs*1000,3)

class DvfsSensor(ApolloEntity, SensorEntity):
    """Values the miner's DVFS tuner prints to its log every few seconds."""
    def __init__(self,entry,coordinator,key,name,field,unit=None,device_class=None,state_class=None,diagnostic=False,precision=None):
        super().__init__(entry,coordinator,key,name)
        self.field=field
        self._attr_native_unit_of_measurement=unit
        self._attr_device_class=device_class
        self._attr_state_class=state_class
        if precision is not None:
            self._attr_suggested_display_precision=precision
        if diagnostic:
            self._attr_entity_category=EntityCategory.DIAGNOSTIC

    @property
    def _dvfs(self):
        return (self.coordinator.data or {}).get('dvfs') or {}

    @property
    def available(self):
        data=self.coordinator.data or {}
        return super().available and not data.get('dvfs_stale') and self.field in self._dvfs

    @property
    def native_value(self):
        return self._dvfs.get(self.field)

DVFS_SPECS = (
    ('dvfs_target_ths','Hashrate target','target_ths','TH/s',None,SensorStateClass.MEASUREMENT,False),
    # The miner logs the voltage to 3 decimals; HA's voltage default rounds it to whole volts.
    ('dvfs_board_voltage','Board voltage','voltage',UnitOfElectricPotential.VOLT,SensorDeviceClass.VOLTAGE,SensorStateClass.MEASUREMENT,False,3),
    ('dvfs_fan_pwm','Fan PWM','fan_pwm',PERCENTAGE,None,SensorStateClass.MEASUREMENT,False),
)

class TuningActivity(ApolloEntity, SensorEntity, RestoreEntity):
    """Whether the DVFS tuner is actually changing anything.

    The miner's own phase label is misleading: in Super ECO it stays at
    TUNE_STEPPING_UP indefinitely while voltage and frequency are constant.
    "Adjusting" means the board voltage setpoint or chip frequency (osc)
    changed, or the tuner logged an action, within TUNING_WINDOW; otherwise
    "Holding". Unknown until it has watched for TUNING_WINDOW.
    """
    _attr_device_class=SensorDeviceClass.ENUM
    _attr_options=['Adjusting','Holding']
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    _attr_icon='mdi:tune-variant'
    TUNING_WINDOW=timedelta(minutes=10)

    def __init__(self,entry,logs,miner):
        super().__init__(entry,logs,'dvfs_tune','Tuning state')
        self.miner=miner
        self._last={}
        self._last_change=None
        self._watch_since=None
        self._last_action=None

    async def async_added_to_hass(self):
        old=await self.async_get_last_state()
        if old is not None:
            try:
                self._last_change=datetime.fromisoformat(old.attributes.get('last_adjustment'))
            except (TypeError,ValueError):
                pass
        await super().async_added_to_hass()
        self.async_on_remove(self.miner.async_add_listener(self._handle_coordinator_update))

    def _observe(self):
        now=dt_util.utcnow()
        if self._watch_since is None:
            self._watch_since=now
        dvfs=(self.coordinator.data or {}).get('dvfs') or {}
        stats=miner_stats(self.miner.data)
        current={'voltage':dvfs.get('voltage'),
                 'osc':at(stats,'master','osc') if stats else None}
        for key,value in current.items():
            if value is None:
                continue
            if key in self._last and self._last[key] != value:
                self._last_change=now
            self._last[key]=value
        action=dvfs.get('last_action')
        if action and action != self._last_action:
            # The log snapshot spans only seconds, so an action in it is recent.
            self._last_change=now
            self._last_action=action

    def _handle_coordinator_update(self):
        self._observe()
        super()._handle_coordinator_update()

    @property
    def available(self):
        return super().available and not (self.coordinator.data or {}).get('dvfs_stale')

    @property
    def native_value(self):
        now=dt_util.utcnow()
        if self._last_change and now-self._last_change < self.TUNING_WINDOW:
            return 'Adjusting'
        if self._watch_since and (now-self._watch_since >= self.TUNING_WINDOW
                                  or self._last_change is not None):
            return 'Holding'
        return None

    @property
    def extra_state_attributes(self):
        dvfs=(self.coordinator.data or {}).get('dvfs') or {}
        return {'tuner_phase':dvfs.get('tune'),'dvfs_state':dvfs.get('state'),
                'board_voltage':self._last.get('voltage'),'frequency_osc':self._last.get('osc'),
                'chip_voltage_avg':dvfs.get('chip_voltage'),'hitrate':dvfs.get('hitrate'),
                'last_tuner_action':self._last_action,
                'last_adjustment':self._last_change.isoformat() if self._last_change else None}

class DiskPercent(ApolloEntity, SensorEntity):
    _attr_native_unit_of_measurement=PERCENTAGE
    _attr_state_class=SensorStateClass.MEASUREMENT
    _attr_entity_category=EntityCategory.DIAGNOSTIC
    def __init__(self,entry,coordinator,index,label):
        super().__init__(entry,coordinator,f'disk_{index}_percent',f'{label} disk utilization')
        self.index=index
    @property
    def native_value(self):
        disks=at(self.coordinator.data or {},'disks') or []
        disk=next((d for d in disks if d.get('mountPoint') == ('/' if self.index==0 else '/var/log')),None)
        if not disk or not disk.get('total'):
            return None
        return round(disk['used']/disk['total']*100,1)

class MiningEnergy(ApolloEntity, SensorEntity, RestoreEntity):
    """Estimate kWh from reported hashboard W; ignore gaps over 60 s."""
    _attr_native_unit_of_measurement='kWh'
    _attr_device_class=SensorDeviceClass.ENERGY
    _attr_state_class=SensorStateClass.TOTAL_INCREASING
    _attr_icon='mdi:lightning-bolt'
    def __init__(self,entry,coordinator):
        super().__init__(entry,coordinator,'hashboard_energy','Hashboard energy estimated')
        self._energy=0.0
        self._last_time=None
        self._last_power=None

    async def async_added_to_hass(self):
        restored=await self.async_get_last_state()
        if restored is not None:
            try:
                self._energy=max(0.0,float(restored.state))
            except (ValueError,TypeError):
                pass
        await super().async_added_to_hass()
        # First observation after a restart establishes the baseline; do not
        # estimate energy for the time HA was not running.
        self._sample()

    def _sample(self):
        now=datetime.now(timezone.utc)
        data=self.coordinator.data or {}
        stats=miner_stats(data)
        power=at(stats,'master','boardsW') if stats else None
        if not isinstance(power,(int,float)) or power < 0:
            self._last_time=None
            self._last_power=None
            return
        if self._last_time is not None and self._last_power is not None:
            dt=(now-self._last_time).total_seconds()
            if 0 < dt <= 60:
                self._energy+=((power+self._last_power)/2)*dt/3600000
        self._last_time=now
        self._last_power=power

    def _handle_coordinator_update(self):
        self._sample()
        super()._handle_coordinator_update()

    @property
    def native_value(self):
        return round(self._energy,6)

    @property
    def extra_state_attributes(self):
        return {'scope':'Reported hashboard power only; excludes controller and PSU losses',
                'gap_handling':'Intervals over 60 seconds or with stale miner stats are excluded'}

async def async_setup_entry(hass,entry,async_add_entities):
    data=hass.data[DOMAIN][entry.entry_id]
    entities=[ApolloSensor(entry,data[spec[2]],spec) for spec in SPECS]
    entities.extend(DiskPercent(entry,data['mcu'],i,label) for i,label in ((0,'Root'),(1,'Log')))
    entities.append(MiningEnergy(entry,data['miner']))
    entities.append(Efficiency1h(entry,data['miner']))
    entities.extend(DvfsSensor(entry,data['logs'],*spec) for spec in DVFS_SPECS)
    entities.append(TuningActivity(entry,data['logs'],data['miner']))
    from .general_errors import (MinerErrorCount, MinerLastError,
                                 MinerLastErrorTime, MinerLastErrorCategory)
    general = data["general_error_monitor"]
    entities.extend((MinerErrorCount(entry, general),
                     MinerLastError(entry, general), MinerLastErrorTime(entry, general),
                     MinerLastErrorCategory(entry, general)))
    async_add_entities(entities)
