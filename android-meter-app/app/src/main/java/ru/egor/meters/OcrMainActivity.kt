package ru.egor.meters

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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class OcrMainActivity : ComponentActivity() {
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
                OcrMeterApp(repository) { callback -> launchCamera(callback) }
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

private data class OcrPreset(val title: String, val unit: String, val kind: String, val icon: String)

private val ocrPresets = listOf(
    OcrPreset("Холодная вода", "м³", "cold_water", "💧"),
    OcrPreset("Горячая вода", "м³", "hot_water", "♨️"),
    OcrPreset("Электричество", "кВт·ч", "electricity", "⚡"),
    OcrPreset("Газ", "м³", "gas", "🔥"),
    OcrPreset("Отопление", "Гкал", "heating", "🌡️"),
    OcrPreset("Другой", "ед.", "other", "◉")
)

@Composable
private fun OcrMeterApp(repository: MeterRepository, onTakePhoto: (((String?) -> Unit) -> Unit)) {
    var addresses by remember { mutableStateOf(repository.load()) }
    var addressId by remember { mutableStateOf<String?>(null) }
    var meterId by remember { mutableStateOf<String?>(null) }

    fun save(value: List<Address>) {
        addresses = value
        repository.save(value)
    }

    val address = addresses.firstOrNull { it.id == addressId }
    val meter = address?.meters?.firstOrNull { it.id == meterId }

    when {
        address == null -> OcrHomeScreen(
            addresses = addresses,
            onOpen = { addressId = it },
            onAdd = { save(addresses + Address(name = it)) },
            onDelete = { id -> save(addresses.filterNot { it.id == id }) }
        )

        meter == null -> OcrAddressScreen(
            address = address,
            onBack = { addressId = null },
            onOpenMeter = { meterId = it },
            onAddMeter = { preset, name, serial ->
                save(addresses.map { a ->
                    if (a.id == address.id) a.copy(meters = a.meters + Meter(name = name, unit = preset.unit, kind = preset.kind, serial = serial)) else a
                })
            },
            onDeleteMeter = { id ->
                save(addresses.map { a ->
                    if (a.id == address.id) a.copy(meters = a.meters.filterNot { it.id == id }) else a
                })
            }
        )

        else -> OcrMeterScreen(
            meter = meter,
            onBack = { meterId = null },
            onTakePhoto = onTakePhoto,
            onAddReading = { value, photo, note ->
                save(addresses.map { a ->
                    if (a.id != address.id) a else a.copy(meters = a.meters.map { m ->
                        if (m.id == meter.id) m.copy(readings = m.readings + Reading(value = value, photoUri = photo, note = note)) else m
                    })
                })
            },
            onDeleteReading = { id ->
                save(addresses.map { a ->
                    if (a.id != address.id) a else a.copy(meters = a.meters.map { m ->
                        if (m.id == meter.id) m.copy(readings = m.readings.filterNot { it.id == id }) else m
                    })
                })
            }
        )
    }
}

@Composable
private fun OcrHomeScreen(addresses: List<Address>, onOpen: (String) -> Unit, onAdd: (String) -> Unit, onDelete: (String) -> Unit) {
    var showAdd by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<Address?>(null) }
    val meters = addresses.sumOf { it.meters.size }
    val readings = addresses.sumOf { a -> a.meters.sumOf { it.readings.size } }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Text("Мои счётчики", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text("Фото, распознавание и история показаний", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OcrSummaryCard("Адресов", addresses.size.toString(), Modifier.weight(1f))
            OcrSummaryCard("Счётчиков", meters.toString(), Modifier.weight(1f))
            OcrSummaryCard("Записей", readings.toString(), Modifier.weight(1f))
        }
        Spacer(Modifier.height(18.dp))

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(addresses, key = { it.id }) { address ->
                Card(onClick = { onOpen(address.id) }, modifier = Modifier.fillMaxWidth()) {
                    Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(address.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                            Text("${address.meters.size} счётчиков", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        TextButton(onClick = { deleteTarget = address }) { Text("Удалить") }
                    }
                }
            }
        }
        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("+ Добавить адрес") }
    }

    if (showAdd) OcrTextDialog("Новый адрес", "Название или адрес", { showAdd = false }) { onAdd(it); showAdd = false }
    deleteTarget?.let { target ->
        OcrConfirmDialog("Удалить адрес?", "Удалятся все счётчики и показания по адресу «${target.name}».", { deleteTarget = null }) {
            onDelete(target.id); deleteTarget = null
        }
    }
}

@Composable
private fun OcrSummaryCard(label: String, value: String, modifier: Modifier) {
    Card(modifier) {
        Column(Modifier.padding(12.dp)) {
            Text(value, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(label, style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun OcrAddressScreen(
    address: Address,
    onBack: () -> Unit,
    onOpenMeter: (String) -> Unit,
    onAddMeter: (OcrPreset, String, String) -> Unit,
    onDeleteMeter: (String) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    var deleteTarget by remember { mutableStateOf<Meter?>(null) }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Все адреса") }
        Text(address.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))

        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            items(address.meters, key = { it.id }) { meter ->
                val sorted = meter.readings.sortedByDescending { it.timestamp }
                val latest = sorted.firstOrNull()
                val previous = sorted.getOrNull(1)
                Card(onClick = { onOpenMeter(meter.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(ocrIcon(meter.kind), style = MaterialTheme.typography.headlineSmall)
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(meter.name, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                                if (meter.serial.isNotBlank()) Text("№ ${meter.serial}", style = MaterialTheme.typography.bodySmall)
                            }
                            TextButton(onClick = { deleteTarget = meter }) { Text("Удалить") }
                        }
                        if (latest != null) {
                            Spacer(Modifier.height(8.dp))
                            Text("${ocrFormat(latest.value)} ${meter.unit}", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
                            if (previous != null) Text("Расход: ${ocrFormat(latest.value - previous.value)} ${meter.unit}")
                            Text(ocrDate(latest.timestamp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        } else {
                            Spacer(Modifier.height(8.dp))
                            Text("Показаний ещё нет", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("+ Добавить счётчик") }
    }

    if (showAdd) OcrAddMeterDialog({ showAdd = false }) { preset, name, serial -> onAddMeter(preset, name, serial); showAdd = false }
    deleteTarget?.let { meter ->
        OcrConfirmDialog("Удалить счётчик?", "История «${meter.name}» тоже будет удалена.", { deleteTarget = null }) {
            onDeleteMeter(meter.id); deleteTarget = null
        }
    }
}

@Composable
private fun OcrMeterScreen(
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
        Text("${ocrIcon(meter.kind)} ${meter.name}", style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        if (meter.serial.isNotBlank()) Text("Серийный номер: ${meter.serial}", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(14.dp))

        Card(Modifier.fillMaxWidth()) {
            Column(Modifier.padding(18.dp)) {
                if (latest == null) {
                    Text("Нет показаний", fontWeight = FontWeight.SemiBold)
                    Text("Сделайте фото — приложение попробует прочитать цифры автоматически.")
                } else {
                    Text("Текущее показание", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("${ocrFormat(latest.value)} ${meter.unit}", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                    Text(ocrDate(latest.timestamp))
                    if (previous != null) {
                        Spacer(Modifier.height(8.dp))
                        Text("Расход: ${ocrFormat(latest.value - previous.value)} ${meter.unit}", fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }

        Spacer(Modifier.height(18.dp))
        Text("История", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(sorted, key = { it.id }) { reading ->
                Card(Modifier.fillMaxWidth()) {
                    Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${ocrFormat(reading.value)} ${meter.unit}", fontWeight = FontWeight.SemiBold)
                            Text(ocrDateTime(reading.timestamp), style = MaterialTheme.typography.bodySmall)
                            if (reading.note.isNotBlank()) Text(reading.note, style = MaterialTheme.typography.bodySmall)
                        }
                        if (reading.photoUri != null) Text("📷")
                        TextButton(onClick = { deleteTarget = reading }) { Text("Удалить") }
                    }
                }
            }
        }
        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("📷 Новое показание") }
    }

    if (showAdd) {
        OcrAddReadingDialog(meter.unit, latest?.value, onTakePhoto, { showAdd = false }) { value, photo, note ->
            onAddReading(value, photo, note); showAdd = false
        }
    }

    deleteTarget?.let { reading ->
        OcrConfirmDialog("Удалить показание?", "Запись ${ocrDate(reading.timestamp)} будет удалена.", { deleteTarget = null }) {
            onDeleteReading(reading.id); deleteTarget = null
        }
    }
}

@Composable
private fun OcrAddReadingDialog(
    unit: String,
    previousValue: Double?,
    onTakePhoto: (((String?) -> Unit) -> Unit),
    onDismiss: () -> Unit,
    onConfirm: (Double, String?, String) -> Unit
) {
    val context = LocalContext.current
    var valueText by remember { mutableStateOf("") }
    var photoUri by remember { mutableStateOf<String?>(null) }
    var note by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var ocrStatus by remember { mutableStateOf<String?>(null) }
    var recognizing by remember { mutableStateOf(false) }
    var allowLower by remember { mutableStateOf(false) }

    val parsed = valueText.replace(',', '.').toDoubleOrNull()
    val isLower = parsed != null && previousValue != null && parsed < previousValue

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новое показание") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (previousValue != null) Text("Предыдущее: ${ocrFormat(previousValue)} $unit")

                Button(
                    onClick = {
                        onTakePhoto { uri ->
                            photoUri = uri
                            if (uri != null) {
                                recognizing = true
                                ocrStatus = "Распознаю показание…"
                                MeterOcr.recognize(context, uri, previousValue) { result ->
                                    recognizing = false
                                    result.onSuccess { value ->
                                        if (value != null) {
                                            valueText = ocrFormat(value)
                                            ocrStatus = "Распознано: ${ocrFormat(value)} $unit. Проверьте цифры перед сохранением."
                                        } else {
                                            ocrStatus = "Число на фото не найдено. Введите показание вручную."
                                        }
                                    }.onFailure {
                                        ocrStatus = "Не удалось распознать фото. Введите показание вручную."
                                    }
                                }
                            }
                        }
                    },
                    enabled = !recognizing,
                    modifier = Modifier.fillMaxWidth()
                ) { Text(if (photoUri == null) "📷 Сфотографировать и распознать" else "📷 Переснять и распознать") }

                ocrStatus?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }

                OutlinedTextField(
                    value = valueText,
                    onValueChange = { valueText = it; error = null },
                    label = { Text("Показание, $unit") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                if (parsed != null && previousValue != null && parsed >= previousValue) {
                    Text("Расход: ${ocrFormat(parsed - previousValue)} $unit", color = MaterialTheme.colorScheme.primary)
                }
                if (isLower) {
                    Text("Значение меньше предыдущего.", color = MaterialTheme.colorScheme.error)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = allowLower, onCheckedChange = { allowLower = it })
                        Text("Счётчик заменён — сохранить всё равно")
                    }
                }

                OutlinedTextField(note, { note = it }, label = { Text("Комментарий — необязательно") }, modifier = Modifier.fillMaxWidth())
                if (photoUri != null) Text("✓ Фото будет сохранено вместе с показанием", style = MaterialTheme.typography.bodySmall)
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
                enabled = parsed != null && !recognizing
            ) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun OcrAddMeterDialog(onDismiss: () -> Unit, onConfirm: (OcrPreset, String, String) -> Unit) {
    var selected by remember { mutableStateOf(ocrPresets.first()) }
    var name by remember { mutableStateOf(selected.title) }
    var serial by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новый счётчик") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ocrPresets.forEach { preset ->
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
private fun OcrTextDialog(title: String, label: String, onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
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
private fun OcrConfirmDialog(title: String, text: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = onConfirm) { Text("Удалить") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

private fun ocrIcon(kind: String): String = ocrPresets.firstOrNull { it.kind == kind }?.icon ?: "◉"
private fun ocrFormat(value: Double): String = if (value % 1.0 == 0.0) value.toLong().toString() else String.format(Locale.getDefault(), "%.3f", value).trimEnd('0').trimEnd(',', '.')
private fun ocrDate(timestamp: Long): String = SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(timestamp))
private fun ocrDateTime(timestamp: Long): String = SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date(timestamp))
