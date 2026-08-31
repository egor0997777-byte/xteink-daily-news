package ru.egor.meters

import android.content.Context
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import kotlin.math.roundToLong

data class Reading(
    val id: String = UUID.randomUUID().toString(),
    val value: Double,
    val timestamp: Long = System.currentTimeMillis(),
    val photoUri: String? = null,
    val note: String = ""
)

data class Meter(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val unit: String,
    val kind: String = "other",
    val serial: String = "",
    val readings: List<Reading> = emptyList()
)

data class Address(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val meters: List<Meter> = emptyList()
)

data class MeterPreset(val title: String, val unit: String, val kind: String, val icon: String)

private val meterPresets = listOf(
    MeterPreset("Холодная вода", "м³", "cold_water", "💧"),
    MeterPreset("Горячая вода", "м³", "hot_water", "♨️"),
    MeterPreset("Электричество", "кВт·ч", "electricity", "⚡"),
    MeterPreset("Газ", "м³", "gas", "🔥"),
    MeterPreset("Отопление", "Гкал", "heating", "🌡️"),
    MeterPreset("Другой", "ед.", "other", "◉")
)

class MeterRepository(context: Context) {
    private val prefs = context.getSharedPreferences("meters", Context.MODE_PRIVATE)

    fun load(): List<Address> {
        val raw = prefs.getString("addresses", null) ?: return emptyList()
        return runCatching {
            val root = JSONArray(raw)
            buildList {
                for (i in 0 until root.length()) {
                    val a = root.getJSONObject(i)
                    val metersJson = a.optJSONArray("meters") ?: JSONArray()
                    val meters = buildList {
                        for (j in 0 until metersJson.length()) {
                            val m = metersJson.getJSONObject(j)
                            val readingsJson = m.optJSONArray("readings") ?: JSONArray()
                            val readings = buildList {
                                for (k in 0 until readingsJson.length()) {
                                    val r = readingsJson.getJSONObject(k)
                                    add(
                                        Reading(
                                            id = r.optString("id", UUID.randomUUID().toString()),
                                            value = r.getDouble("value"),
                                            timestamp = r.optLong("timestamp", System.currentTimeMillis()),
                                            photoUri = r.optString("photoUri").takeIf { it.isNotBlank() },
                                            note = r.optString("note", "")
                                        )
                                    )
                                }
                            }
                            add(
                                Meter(
                                    id = m.optString("id", UUID.randomUUID().toString()),
                                    name = m.optString("name", "Счётчик"),
                                    unit = m.optString("unit", "ед."),
                                    kind = m.optString("kind", inferKind(m.optString("name", ""))),
                                    serial = m.optString("serial", ""),
                                    readings = readings
                                )
                            )
                        }
                    }
                    add(Address(id = a.optString("id", UUID.randomUUID().toString()), name = a.optString("name", "Адрес"), meters = meters))
                }
            }
        }.getOrDefault(emptyList())
    }

    fun save(addresses: List<Address>) {
        val root = JSONArray()
        addresses.forEach { address ->
            val metersJson = JSONArray()
            address.meters.forEach { meter ->
                val readingsJson = JSONArray()
                meter.readings.forEach { reading ->
                    readingsJson.put(
                        JSONObject()
                            .put("id", reading.id)
                            .put("value", reading.value)
                            .put("timestamp", reading.timestamp)
                            .put("photoUri", reading.photoUri ?: "")
                            .put("note", reading.note)
                    )
                }
                metersJson.put(
                    JSONObject()
                        .put("id", meter.id)
                        .put("name", meter.name)
                        .put("unit", meter.unit)
                        .put("kind", meter.kind)
                        .put("serial", meter.serial)
                        .put("readings", readingsJson)
                )
            }
            root.put(
                JSONObject()
                    .put("id", address.id)
                    .put("name", address.name)
                    .put("meters", metersJson)
            )
        }
        prefs.edit().putString("addresses", root.toString()).apply()
    }
}

class MainActivity : ComponentActivity() {
    private var pendingPhotoUri: Uri? = null
    private var pendingPhotoCallback: ((String?) -> Unit)? = null

    private val cameraLauncher = registerForActivityResult(ActivityResultContracts.TakePicture()) { success ->
        val uri = pendingPhotoUri
        pendingPhotoCallback?.invoke(if (success && uri != null) uri.toString() else null)
        pendingPhotoUri = null
        pendingPhotoCallback = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val repository = MeterRepository(this)
        setContent {
            MaterialTheme {
                MeterApp(repository) { callback -> launchCamera(callback) }
            }
        }
    }

    private fun launchCamera(callback: (String?) -> Unit) {
        val picturesDir = getExternalFilesDir(Environment.DIRECTORY_PICTURES) ?: filesDir
        val file = File(picturesDir, "meter_${System.currentTimeMillis()}.jpg")
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        pendingPhotoUri = uri
        pendingPhotoCallback = callback
        cameraLauncher.launch(uri)
    }
}

@Composable
fun MeterApp(repository: MeterRepository, onTakePhoto: (((String?) -> Unit) -> Unit)) {
    var addresses by remember { mutableStateOf(repository.load()) }
    var selectedAddressId by remember { mutableStateOf<String?>(null) }
    var selectedMeterId by remember { mutableStateOf<String?>(null) }

    fun persist(newAddresses: List<Address>) {
        addresses = newAddresses
        repository.save(newAddresses)
    }

    val selectedAddress = addresses.firstOrNull { it.id == selectedAddressId }
    val selectedMeter = selectedAddress?.meters?.firstOrNull { it.id == selectedMeterId }

    Surface(Modifier.fillMaxSize()) {
        when {
            selectedAddress == null -> HomeScreen(
                addresses = addresses,
                onOpen = { selectedAddressId = it },
                onAdd = { persist(addresses + Address(name = it)) },
                onDelete = { id -> persist(addresses.filterNot { it.id == id }) }
            )

            selectedMeter == null -> AddressScreen(
                address = selectedAddress,
                onBack = { selectedAddressId = null },
                onOpenMeter = { selectedMeterId = it },
                onAddMeter = { preset, name, serial ->
                    persist(addresses.map { address ->
                        if (address.id == selectedAddress.id) {
                            address.copy(meters = address.meters + Meter(name = name, unit = preset.unit, kind = preset.kind, serial = serial))
                        } else address
                    })
                },
                onDeleteMeter = { meterId ->
                    persist(addresses.map { address ->
                        if (address.id == selectedAddress.id) address.copy(meters = address.meters.filterNot { it.id == meterId }) else address
                    })
                }
            )

            else -> MeterScreen(
                meter = selectedMeter,
                onBack = { selectedMeterId = null },
                onTakePhoto = onTakePhoto,
                onAddReading = { value, photo, note ->
                    persist(addresses.map { address ->
                        if (address.id != selectedAddress.id) return@map address
                        address.copy(meters = address.meters.map { meter ->
                            if (meter.id == selectedMeter.id) meter.copy(readings = meter.readings + Reading(value = value, photoUri = photo, note = note)) else meter
                        })
                    })
                },
                onDeleteReading = { readingId ->
                    persist(addresses.map { address ->
                        if (address.id != selectedAddress.id) return@map address
                        address.copy(meters = address.meters.map { meter ->
                            if (meter.id == selectedMeter.id) meter.copy(readings = meter.readings.filterNot { it.id == readingId }) else meter
                        })
                    })
                }
            )
        }
    }
}

@Composable
private fun HomeScreen(
    addresses: List<Address>,
    onOpen: (String) -> Unit,
    onAdd: (String) -> Unit,
    onDelete: (String) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<Address?>(null) }
    val meterCount = addresses.sumOf { it.meters.size }
    val readingCount = addresses.sumOf { address -> address.meters.sumOf { it.readings.size } }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Text("Мои счётчики", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("Все показания дома — в одном месте", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(16.dp))

        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            SummaryCard("Адресов", addresses.size.toString(), Modifier.weight(1f))
            SummaryCard("Счётчиков", meterCount.toString(), Modifier.weight(1f))
            SummaryCard("Записей", readingCount.toString(), Modifier.weight(1f))
        }
        Spacer(Modifier.height(20.dp))

        if (addresses.isEmpty()) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(20.dp)) {
                    Text("Начнём с адреса", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(6.dp))
                    Text("Добавьте квартиру, дом, дачу или объект. Внутри можно создать сколько угодно счётчиков.")
                }
            }
            Spacer(Modifier.height(16.dp))
        }

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(addresses, key = { it.id }) { address ->
                val latest = address.meters.flatMap { it.readings }.maxByOrNull { it.timestamp }
                Card(onClick = { onOpen(address.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(address.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                Text("${address.meters.size} ${pluralMeters(address.meters.size)}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            TextButton(onClick = { deleteTarget = address }) { Text("Удалить") }
                        }
                        if (latest != null) {
                            Spacer(Modifier.height(6.dp))
                            Text("Последнее обновление: ${formatDate(latest.timestamp)} · ${daysAgoText(latest.timestamp)}", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("+ Добавить адрес") }
    }

    if (showAdd) {
        TextEntryDialog("Новый адрес", "Например: Квартира на Красноказарменной", { showAdd = false }) {
            onAdd(it); showAdd = false
        }
    }

    deleteTarget?.let { target ->
        ConfirmDeleteDialog("Удалить адрес?", "Будут удалены все счётчики и показания по адресу «${target.name}».", { deleteTarget = null }) {
            onDelete(target.id); deleteTarget = null
        }
    }
}

@Composable
private fun SummaryCard(label: String, value: String, modifier: Modifier = Modifier) {
    Card(modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun AddressScreen(
    address: Address,
    onBack: () -> Unit,
    onOpenMeter: (String) -> Unit,
    onAddMeter: (MeterPreset, String, String) -> Unit,
    onDeleteMeter: (String) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<Meter?>(null) }
    val completed = address.meters.count { it.readings.isNotEmpty() }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Все адреса") }
        Text(address.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Text("$completed из ${address.meters.size} счётчиков имеют показания", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(16.dp))

        if (address.meters.isEmpty()) {
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(18.dp)) {
                    Text("Добавьте первый счётчик", fontWeight = FontWeight.SemiBold)
                    Text("Есть готовые шаблоны для воды, электричества, газа и отопления.", color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(Modifier.height(14.dp))
        }

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(address.meters, key = { it.id }) { meter ->
                val sorted = meter.readings.sortedByDescending { it.timestamp }
                val latest = sorted.firstOrNull()
                val previous = sorted.getOrNull(1)
                Card(onClick = { onOpenMeter(meter.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(meterIcon(meter.kind), style = MaterialTheme.typography.headlineSmall)
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(meter.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                                if (meter.serial.isNotBlank()) Text("№ ${meter.serial}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            TextButton(onClick = { deleteTarget = meter }) { Text("Удалить") }
                        }
                        Spacer(Modifier.height(8.dp))
                        if (latest == null) {
                            Text("Показаний ещё нет", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        } else {
                            Text("${formatValue(latest.value)} ${meter.unit}", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                            if (previous != null) {
                                val delta = latest.value - previous.value
                                Text("Расход: ${formatValue(delta)} ${meter.unit} с прошлого раза")
                            }
                            Text("${formatDate(latest.timestamp)} · ${daysAgoText(latest.timestamp)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("+ Добавить счётчик") }
    }

    if (showAdd) AddMeterDialog({ showAdd = false }) { preset, name, serial ->
        onAddMeter(preset, name, serial); showAdd = false
    }

    deleteTarget?.let { meter ->
        ConfirmDeleteDialog("Удалить счётчик?", "История «${meter.name}» тоже будет удалена.", { deleteTarget = null }) {
            onDeleteMeter(meter.id); deleteTarget = null
        }
    }
}

@Composable
private fun MeterScreen(
    meter: Meter,
    onBack: () -> Unit,
    onTakePhoto: (((String?) -> Unit) -> Unit),
    onAddReading: (Double, String?, String) -> Unit,
    onDeleteReading: (String) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<Reading?>(null) }
    val sorted = meter.readings.sortedByDescending { it.timestamp }
    val latest = sorted.firstOrNull()
    val previous = sorted.getOrNull(1)

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Счётчики") }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(meterIcon(meter.kind), style = MaterialTheme.typography.headlineMedium)
            Spacer(Modifier.width(10.dp))
            Column {
                Text(meter.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                if (meter.serial.isNotBlank()) Text("Серийный номер: ${meter.serial}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        Spacer(Modifier.height(16.dp))

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(18.dp)) {
                if (latest == null) {
                    Text("Нет показаний", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Text("Сфотографируйте счётчик и внесите первое значение.")
                } else {
                    Text("Текущее показание", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("${formatValue(latest.value)} ${meter.unit}", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    Text("${formatDate(latest.timestamp)} · ${daysAgoText(latest.timestamp)}")
                    if (previous != null) {
                        Spacer(Modifier.height(10.dp))
                        val delta = latest.value - previous.value
                        Text("Расход за период", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text("${formatValue(delta)} ${meter.unit}", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        Text("История показаний", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(sorted, key = { it.id }) { reading ->
                val index = sorted.indexOf(reading)
                val older = sorted.getOrNull(index + 1)
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(14.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("${formatValue(reading.value)} ${meter.unit}", fontWeight = FontWeight.SemiBold)
                                Text(formatDateTime(reading.timestamp), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                            }
                            if (reading.photoUri != null) Text("📷")
                            TextButton(onClick = { deleteTarget = reading }) { Text("Удалить") }
                        }
                        if (older != null) {
                            val delta = reading.value - older.value
                            Text("+${formatValue(delta)} ${meter.unit} за период", style = MaterialTheme.typography.bodySmall)
                        }
                        if (reading.note.isNotBlank()) Text(reading.note, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("+ Новое показание") }
    }

    if (showAdd) {
        AddReadingDialog(meter.unit, latest?.value, onTakePhoto, { showAdd = false }) { value, photo, note ->
            onAddReading(value, photo, note); showAdd = false
        }
    }

    deleteTarget?.let { reading ->
        ConfirmDeleteDialog("Удалить показание?", "Запись ${formatDate(reading.timestamp)} будет удалена.", { deleteTarget = null }) {
            onDeleteReading(reading.id); deleteTarget = null
        }
    }
}

@Composable
private fun AddMeterDialog(onDismiss: () -> Unit, onConfirm: (MeterPreset, String, String) -> Unit) {
    var selected by remember { mutableStateOf(meterPresets.first()) }
    var name by remember { mutableStateOf(selected.title) }
    var serial by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новый счётчик") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Тип", fontWeight = FontWeight.SemiBold)
                meterPresets.forEach { preset ->
                    FilterChip(
                        selected = selected.kind == preset.kind,
                        onClick = { selected = preset; name = preset.title },
                        label = { Text("${preset.icon} ${preset.title} · ${preset.unit}") },
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                OutlinedTextField(name, { name = it }, label = { Text("Название") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(serial, { serial = it }, label = { Text("Серийный номер — необязательно") }, singleLine = true, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = { TextButton(onClick = { onConfirm(selected, name.trim(), serial.trim()) }, enabled = name.isNotBlank()) { Text("Добавить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun AddReadingDialog(
    unit: String,
    previousValue: Double?,
    onTakePhoto: (((String?) -> Unit) -> Unit),
    onDismiss: () -> Unit,
    onConfirm: (Double, String?, String) -> Unit
) {
    var valueText by remember { mutableStateOf("") }
    var photoUri by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var allowLower by remember { mutableStateOf(false) }
    val parsed = valueText.replace(',', '.').toDoubleOrNull()
    val isLower = parsed != null && previousValue != null && parsed < previousValue

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новое показание") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (previousValue != null) Text("Предыдущее: ${formatValue(previousValue)} $unit")
                OutlinedTextField(
                    value = valueText,
                    onValueChange = { valueText = it; error = null },
                    label = { Text("Показание, $unit") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
                if (parsed != null && previousValue != null && parsed >= previousValue) {
                    Text("Расход: ${formatValue(parsed - previousValue)} $unit", color = MaterialTheme.colorScheme.primary)
                }
                if (isLower) {
                    Text("Значение меньше предыдущего. Возможно, счётчик заменили или допущена ошибка.", color = MaterialTheme.colorScheme.error)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = allowLower, onCheckedChange = { allowLower = it })
                        Text("Счётчик заменён — сохранить всё равно")
                    }
                }
                OutlinedTextField(note, { note = it }, label = { Text("Комментарий — необязательно") }, modifier = Modifier.fillMaxWidth())
                OutlinedButton(onClick = { onTakePhoto { uri -> photoUri = uri } }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (photoUri == null) "📷 Сфотографировать счётчик" else "✓ Фото добавлено — переснять")
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    when {
                        parsed == null -> error = "Введите корректное число"
                        parsed < 0 -> error = "Показание не может быть отрицательным"
                        isLower && !allowLower -> error = "Подтвердите замену счётчика или исправьте значение"
                        else -> onConfirm(parsed, photoUri, note.trim())
                    }
                },
                enabled = parsed != null
            ) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun TextEntryDialog(title: String, label: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { OutlinedTextField(text, { text = it }, label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth()) },
        confirmButton = { TextButton(onClick = { onConfirm(text.trim()) }, enabled = text.isNotBlank()) { Text("Сохранить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun ConfirmDeleteDialog(title: String, text: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = onConfirm) { Text("Удалить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

private fun meterIcon(kind: String): String = meterPresets.firstOrNull { it.kind == kind }?.icon ?: "◉"

private fun inferKind(name: String): String {
    val n = name.lowercase(Locale.getDefault())
    return when {
        "холод" in n -> "cold_water"
        "горяч" in n -> "hot_water"
        "элект" in n -> "electricity"
        "газ" in n -> "gas"
        "отоп" in n || "тепл" in n -> "heating"
        else -> "other"
    }
}

private fun formatValue(value: Double): String = if (value == value.roundToLong().toDouble()) value.roundToLong().toString() else String.format(Locale.getDefault(), "%.3f", value).trimEnd('0').trimEnd(',', '.')

private fun formatDate(timestamp: Long): String = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(timestamp))
private fun formatDateTime(timestamp: Long): String = SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date(timestamp))

private fun daysAgoText(timestamp: Long): String {
    val days = ((System.currentTimeMillis() - timestamp).coerceAtLeast(0L) / 86_400_000L).toInt()
    return when (days) {
        0 -> "сегодня"
        1 -> "вчера"
        in 2..4 -> "$days дня назад"
        else -> "$days дней назад"
    }
}

private fun pluralMeters(count: Int): String {
    val n10 = count % 10
    val n100 = count % 100
    return when {
        n10 == 1 && n100 != 11 -> "счётчик"
        n10 in 2..4 && n100 !in 12..14 -> "счётчика"
        else -> "счётчиков"
    }
}
