package ru.egor.meters

import android.net.Uri
import android.os.Bundle
import android.os.Environment
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val Accent = Color(0xFF6E5BC7)
private val AppBg = Color(0xFFF7F7FA)
private val SoftSurface = Color(0xFFF0EFF4)
private val Hairline = Color(0xFFE5E3EA)
private val Muted = Color(0xFF74717D)
private val Danger = Color(0xFFC93B46)

private val MeterColors = lightColorScheme(
    primary = Accent,
    onPrimary = Color.White,
    background = AppBg,
    onBackground = Color(0xFF111114),
    surface = Color.White,
    onSurface = Color(0xFF111114),
    surfaceVariant = SoftSurface,
    onSurfaceVariant = Muted,
    outline = Hairline,
    error = Danger
)

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
            MaterialTheme(colorScheme = MeterColors) {
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

private data class MeterPreset(val title: String, val unit: String, val kind: String, val mark: String)

private val presets = listOf(
    MeterPreset("Холодная вода", "м³", "cold_water", "ХВ"),
    MeterPreset("Горячая вода", "м³", "hot_water", "ГВ"),
    MeterPreset("Электричество", "кВт·ч", "electricity", "ЭЭ"),
    MeterPreset("Газ", "м³", "gas", "Г"),
    MeterPreset("Отопление", "Гкал", "heating", "Т"),
    MeterPreset("Другой", "ед.", "other", "•")
)

@Composable
private fun MeterApp(repository: MeterRepository, onTakePhoto: (((String?) -> Unit) -> Unit)) {
    var addresses by remember { mutableStateOf(repository.load()) }
    var addressId by remember { mutableStateOf<String?>(null) }
    var meterId by remember { mutableStateOf<String?>(null) }

    fun save(value: List<Address>) {
        addresses = value
        repository.save(value)
    }

    val address = addresses.firstOrNull { it.id == addressId }
    val meter = address?.meters?.firstOrNull { it.id == meterId }

    Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
        when {
            address == null -> HomeScreen(
                addresses = addresses,
                onOpen = { addressId = it },
                onAdd = { save(addresses + Address(name = it)) },
                onDelete = { id -> save(addresses.filterNot { it.id == id }) }
            )

            meter == null -> AddressScreen(
                address = address,
                onBack = { addressId = null },
                onOpenMeter = { meterId = it },
                onAddMeter = { preset, name, serial ->
                    save(addresses.map { a ->
                        if (a.id == address.id) a.copy(
                            meters = a.meters + Meter(name = name, unit = preset.unit, kind = preset.kind, serial = serial)
                        ) else a
                    })
                },
                onDeleteMeter = { id ->
                    save(addresses.map { a ->
                        if (a.id == address.id) a.copy(meters = a.meters.filterNot { it.id == id }) else a
                    })
                }
            )

            else -> MeterScreen(
                meter = meter,
                onBack = { meterId = null },
                onTakePhoto = onTakePhoto,
                onAddReading = { value, photo, note ->
                    save(addresses.map { a ->
                        if (a.id != address.id) a else a.copy(meters = a.meters.map { m ->
                            if (m.id == meter.id) m.copy(
                                readings = m.readings + Reading(value = value, photoUri = photo, note = note)
                            ) else m
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
}

@Composable
private fun ScreenFrame(content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .statusBarsPadding()
            .navigationBarsPadding()
            .padding(horizontal = 20.dp, vertical = 8.dp),
        content = content
    )
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
    val meters = addresses.sumOf { it.meters.size }
    val readings = addresses.sumOf { a -> a.meters.sumOf { it.readings.size } }

    ScreenFrame {
        Spacer(Modifier.height(4.dp))
        Text("Мои счётчики", fontSize = 30.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold)
        Text("Все показания в одном месте", color = Muted, fontSize = 15.sp)
        Spacer(Modifier.height(18.dp))

        if (addresses.isNotEmpty()) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(18.dp),
                color = SoftSurface
            ) {
                Row(
                    Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    CompactStat(addresses.size.toString(), "адресов")
                    StatDot()
                    CompactStat(meters.toString(), "счётчиков")
                    StatDot()
                    CompactStat(readings.toString(), "записей")
                }
            }
            Spacer(Modifier.height(22.dp))
            Text("Адреса", fontSize = 20.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(10.dp))

            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(addresses, key = { it.id }) { address ->
                    val latest = address.meters.flatMap { it.readings }.maxByOrNull { it.timestamp }
                    Card(
                        onClick = { onOpen(address.id) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(20.dp),
                        colors = CardDefaults.cardColors(containerColor = Color.White)
                    ) {
                        Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                            CircleMark("⌂")
                            Spacer(Modifier.width(13.dp))
                            Column(Modifier.weight(1f)) {
                                Text(address.name, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                                val subtitle = if (address.meters.isEmpty()) {
                                    "Счётчиков пока нет"
                                } else {
                                    "${address.meters.size} ${pluralMeter(address.meters.size)}"
                                }
                                Text(subtitle, color = Muted, fontSize = 13.sp)
                                if (latest != null) Text("Обновлено ${formatDate(latest.timestamp)}", color = Muted, fontSize = 12.sp)
                            }
                            TextButton(onClick = { deleteTarget = address }) { Text("•••", color = Muted, fontSize = 18.sp) }
                        }
                    }
                }
            }
        } else {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(horizontal = 28.dp)) {
                    Box(
                        Modifier.size(64.dp).background(Accent.copy(alpha = 0.10f), RoundedCornerShape(32.dp)),
                        contentAlignment = Alignment.Center
                    ) { Text("⌂", color = Accent, fontSize = 27.sp, fontWeight = FontWeight.Bold) }
                    Spacer(Modifier.height(18.dp))
                    Text("Начните с адреса", fontSize = 21.sp, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Добавьте квартиру, дом или дачу. Затем подключите счётчики и сохраняйте показания.",
                        color = Muted,
                        fontSize = 15.sp,
                        lineHeight = 21.sp
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        PrimaryButton("Добавить адрес") { showAdd = true }
    }

    if (showAdd) TextEntryDialog(
        title = "Новый адрес",
        label = "Название или адрес",
        placeholder = "Например, Квартира",
        confirmTitle = "Добавить",
        onDismiss = { showAdd = false },
        onConfirm = { onAdd(it); showAdd = false }
    )

    deleteTarget?.let { target ->
        ConfirmDialog(
            title = "Удалить адрес?",
            text = "Все счётчики и показания по адресу «${target.name}» будут удалены.",
            onDismiss = { deleteTarget = null },
            onConfirm = { onDelete(target.id); deleteTarget = null }
        )
    }
}

@Composable
private fun CompactStat(value: String, label: String) {
    Row(verticalAlignment = Alignment.Baseline) {
        Text(value, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.width(4.dp))
        Text(label, fontSize = 12.sp, color = Muted)
    }
}

@Composable
private fun StatDot() {
    Box(Modifier.size(4.dp).background(Hairline, RoundedCornerShape(2.dp)))
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

    ScreenFrame {
        BackLink("Все адреса", onBack)
        Text(address.name, fontSize = 29.sp, fontWeight = FontWeight.Bold)
        Text("${address.meters.size} ${pluralMeter(address.meters.size)}", color = Muted, fontSize = 15.sp)
        Spacer(Modifier.height(16.dp))

        if (address.meters.isEmpty()) {
            Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                EmptyHint("Добавьте счётчик", "Выберите тип и при необходимости укажите серийный номер.")
            }
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                items(address.meters, key = { it.id }) { meter ->
                    val sorted = meter.readings.sortedByDescending { it.timestamp }
                    val latest = sorted.firstOrNull()
                    val previous = sorted.getOrNull(1)
                    Card(
                        onClick = { onOpenMeter(meter.id) },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(20.dp),
                        colors = CardDefaults.cardColors(containerColor = Color.White)
                    ) {
                        Column(Modifier.padding(16.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                MeterBadge(meter.kind)
                                Spacer(Modifier.width(12.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(meter.name, fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                                    if (meter.serial.isNotBlank()) Text("№ ${meter.serial}", color = Muted, fontSize = 12.sp)
                                }
                                TextButton(onClick = { deleteTarget = meter }) { Text("•••", color = Muted, fontSize = 18.sp) }
                            }
                            Spacer(Modifier.height(8.dp))
                            if (latest == null) {
                                Text("Нет показаний", color = Muted, fontSize = 14.sp)
                            } else {
                                Text("${formatValue(latest.value)} ${meter.unit}", fontSize = 26.sp, fontWeight = FontWeight.Bold)
                                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                                    Text(formatDate(latest.timestamp), color = Muted, fontSize = 12.sp)
                                    if (previous != null) Text(
                                        "Расход ${formatValue(latest.value - previous.value)} ${meter.unit}",
                                        color = Muted,
                                        fontSize = 12.sp
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        PrimaryButton("Добавить счётчик") { showAdd = true }
    }

    if (showAdd) AddMeterDialog(
        onDismiss = { showAdd = false },
        onConfirm = { preset, name, serial -> onAddMeter(preset, name, serial); showAdd = false }
    )

    deleteTarget?.let { meter ->
        ConfirmDialog(
            title = "Удалить счётчик?",
            text = "История «${meter.name}» тоже будет удалена.",
            onDismiss = { deleteTarget = null },
            onConfirm = { onDeleteMeter(meter.id); deleteTarget = null }
        )
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

    ScreenFrame {
        BackLink("Счётчики", onBack)
        Row(verticalAlignment = Alignment.CenterVertically) {
            MeterBadge(meter.kind)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(meter.name, fontSize = 28.sp, fontWeight = FontWeight.Bold)
                if (meter.serial.isNotBlank()) Text("№ ${meter.serial}", color = Muted, fontSize = 13.sp)
            }
        }
        Spacer(Modifier.height(16.dp))

        Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(22.dp), color = Color.White) {
            Column(Modifier.padding(18.dp)) {
                Text("Текущее показание", color = Muted, fontSize = 13.sp)
                if (latest == null) {
                    Text("—", fontSize = 38.sp, fontWeight = FontWeight.Bold)
                    Text("Добавьте первое показание", color = Muted, fontSize = 14.sp)
                } else {
                    Text("${formatValue(latest.value)} ${meter.unit}", fontSize = 35.sp, fontWeight = FontWeight.Bold)
                    Text(formatDate(latest.timestamp), color = Muted, fontSize = 13.sp)
                    if (previous != null) {
                        Spacer(Modifier.height(12.dp))
                        HorizontalDivider(color = Hairline)
                        Spacer(Modifier.height(12.dp))
                        Text("Расход с прошлого раза", color = Muted, fontSize = 13.sp)
                        Text("${formatValue(latest.value - previous.value)} ${meter.unit}", fontSize = 20.sp, fontWeight = FontWeight.SemiBold)
                    }
                }
            }
        }

        Spacer(Modifier.height(20.dp))
        Text("История", fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(9.dp))

        if (sorted.isEmpty()) {
            Text("Здесь появятся сохранённые показания.", color = Muted, fontSize = 14.sp)
            Spacer(Modifier.weight(1f))
        } else {
            LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                items(sorted, key = { it.id }) { reading ->
                    Surface(Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp), color = Color.White) {
                        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text("${formatValue(reading.value)} ${meter.unit}", fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
                                Text(formatDateTime(reading.timestamp), color = Muted, fontSize = 12.sp)
                                if (reading.note.isNotBlank()) Text(reading.note, color = Muted, fontSize = 12.sp)
                            }
                            if (reading.photoUri != null) Text("Фото", color = Accent, fontSize = 12.sp)
                            TextButton(onClick = { deleteTarget = reading }) { Text("•••", color = Muted, fontSize = 18.sp) }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        PrimaryButton("Новое показание") { showAdd = true }
    }

    if (showAdd) AddReadingDialog(
        meter = meter,
        previousValue = latest?.value,
        onTakePhoto = onTakePhoto,
        onDismiss = { showAdd = false },
        onConfirm = { value, photo, note -> onAddReading(value, photo, note); showAdd = false }
    )

    deleteTarget?.let { reading ->
        ConfirmDialog(
            title = "Удалить показание?",
            text = "Запись от ${formatDate(reading.timestamp)} будет удалена.",
            onDismiss = { deleteTarget = null },
            onConfirm = { onDeleteReading(reading.id); deleteTarget = null }
        )
    }
}

@Composable
private fun AddMeterDialog(onDismiss: () -> Unit, onConfirm: (MeterPreset, String, String) -> Unit) {
    var selected by remember { mutableStateOf(presets.first()) }
    var name by remember { mutableStateOf(selected.title) }
    var serial by remember { mutableStateOf("") }

    Dialog(onDismissRequest = onDismiss) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 690.dp),
            shape = RoundedCornerShape(28.dp),
            color = Color.White
        ) {
            Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState())) {
                Text("Новый счётчик", fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text("Выберите тип", color = Muted, fontSize = 14.sp)
                Spacer(Modifier.height(15.dp))

                presets.chunked(2).forEach { row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                        row.forEach { preset ->
                            val active = selected.kind == preset.kind
                            Surface(
                                onClick = { selected = preset; name = preset.title },
                                modifier = Modifier.weight(1f),
                                shape = RoundedCornerShape(17.dp),
                                color = if (active) Accent.copy(alpha = 0.12f) else SoftSurface,
                                border = if (active) BorderStroke(1.dp, Accent) else null
                            ) {
                                Column(Modifier.padding(13.dp)) {
                                    Text(preset.mark, color = Accent, fontWeight = FontWeight.Bold)
                                    Spacer(Modifier.height(5.dp))
                                    Text(preset.title, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                    Text(preset.unit, color = Muted, fontSize = 11.sp)
                                }
                            }
                        }
                    }
                    Spacer(Modifier.height(9.dp))
                }

                AppTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = "Название",
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Next)
                )
                Spacer(Modifier.height(11.dp))
                AppTextField(
                    value = serial,
                    onValueChange = { serial = it.take(40) },
                    label = "Серийный номер",
                    placeholder = "Необязательно",
                    supporting = "Цифры, русские и английские буквы",
                    keyboardOptions = KeyboardOptions(
                        capitalization = KeyboardCapitalization.Characters,
                        keyboardType = KeyboardType.Text,
                        imeAction = ImeAction.Done,
                        autoCorrectEnabled = false
                    )
                )
                ModalActions(
                    onCancel = onDismiss,
                    onConfirm = { onConfirm(selected, name.trim(), serial.trim()) },
                    confirmTitle = "Добавить",
                    enabled = name.isNotBlank()
                )
            }
        }
    }
}

@Composable
private fun AddReadingDialog(
    meter: Meter,
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

    Dialog(onDismissRequest = { if (!recognizing) onDismiss() }) {
        Surface(
            modifier = Modifier.fillMaxWidth().heightIn(max = 720.dp),
            shape = RoundedCornerShape(28.dp),
            color = Color.White
        ) {
            Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState())) {
                Text("Новое показание", fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Text(meter.name, color = Muted, fontSize = 14.sp)
                Spacer(Modifier.height(16.dp))

                Surface(
                    onClick = {
                        if (!recognizing) {
                            onTakePhoto { uri ->
                                photoUri = uri
                                if (uri != null) {
                                    recognizing = true
                                    ocrStatus = "Распознаю цифры…"
                                    MeterOcr.recognize(context, uri, previousValue) { result ->
                                        recognizing = false
                                        result.onSuccess { value ->
                                            if (value != null) {
                                                valueText = formatValue(value)
                                                ocrStatus = "Распознано автоматически. Проверьте значение."
                                            } else {
                                                ocrStatus = "Не удалось уверенно найти показание. Введите вручную."
                                            }
                                        }.onFailure {
                                            ocrStatus = "Не удалось распознать фото. Введите вручную."
                                        }
                                    }
                                }
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(20.dp),
                    color = SoftSurface
                ) {
                    Column(Modifier.padding(18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(if (photoUri == null) "Сделать фото" else "Переснять фото", color = Accent, fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                        Text(if (photoUri == null) "Распознаю показание автоматически" else "Фото добавлено к записи", color = Muted, fontSize = 12.sp)
                    }
                }

                if (recognizing) {
                    Spacer(Modifier.height(10.dp))
                    LinearProgressIndicator(Modifier.fillMaxWidth())
                }
                ocrStatus?.let {
                    Spacer(Modifier.height(7.dp))
                    Text(it, color = Muted, fontSize = 12.sp)
                }

                Spacer(Modifier.height(16.dp))
                Text("Показание", color = Muted, fontSize = 13.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = valueText,
                        onValueChange = { raw -> valueText = sanitizeNumber(raw); error = null },
                        modifier = Modifier.weight(1f),
                        textStyle = LocalTextStyle.current.copy(fontSize = 28.sp, fontWeight = FontWeight.SemiBold),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal, imeAction = ImeAction.Done),
                        singleLine = true,
                        shape = RoundedCornerShape(17.dp),
                        placeholder = { Text("0") }
                    )
                    Spacer(Modifier.width(10.dp))
                    Text(meter.unit, color = Muted, fontSize = 15.sp)
                }

                if (previousValue != null) {
                    Spacer(Modifier.height(7.dp))
                    Text("Предыдущее: ${formatValue(previousValue)} ${meter.unit}", color = Muted, fontSize = 12.sp)
                }
                if (parsed != null && previousValue != null && parsed >= previousValue) {
                    Text("Расход: ${formatValue(parsed - previousValue)} ${meter.unit}", color = Accent, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                }
                if (isLower) {
                    Spacer(Modifier.height(7.dp))
                    Text("Значение меньше предыдущего", color = Danger, fontSize = 13.sp)
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = allowLower, onCheckedChange = { allowLower = it })
                        Text("Счётчик заменён", fontSize = 13.sp)
                    }
                }

                Spacer(Modifier.height(12.dp))
                AppTextField(
                    value = note,
                    onValueChange = { note = it.take(200) },
                    label = "Комментарий",
                    placeholder = "Необязательно",
                    singleLine = false,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences)
                )
                error?.let {
                    Spacer(Modifier.height(7.dp))
                    Text(it, color = Danger, fontSize = 12.sp)
                }
                ModalActions(
                    onCancel = onDismiss,
                    onConfirm = {
                        when {
                            parsed == null -> error = "Введите показание"
                            parsed < 0 -> error = "Показание не может быть отрицательным"
                            isLower && !allowLower -> error = "Подтвердите замену счётчика"
                            else -> onConfirm(parsed, photoUri, note.trim())
                        }
                    },
                    confirmTitle = "Сохранить",
                    enabled = parsed != null && !recognizing
                )
            }
        }
    }
}

@Composable
private fun TextEntryDialog(
    title: String,
    label: String,
    placeholder: String,
    confirmTitle: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    var text by remember { mutableStateOf("") }
    Dialog(onDismissRequest = onDismiss) {
        Surface(shape = RoundedCornerShape(28.dp), color = Color.White, modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(20.dp)) {
                Text(title, fontSize = 26.sp, fontWeight = FontWeight.Bold)
                Spacer(Modifier.height(16.dp))
                AppTextField(
                    value = text,
                    onValueChange = { text = it },
                    label = label,
                    placeholder = placeholder,
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Sentences, imeAction = ImeAction.Done)
                )
                ModalActions(
                    onCancel = onDismiss,
                    onConfirm = { onConfirm(text.trim()) },
                    confirmTitle = confirmTitle,
                    enabled = text.isNotBlank()
                )
            }
        }
    }
}

@Composable
private fun AppTextField(
    value: String,
    onValueChange: (String) -> Unit,
    label: String,
    placeholder: String = "",
    supporting: String? = null,
    singleLine: Boolean = true,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValueChange,
        modifier = Modifier.fillMaxWidth(),
        label = { Text(label) },
        placeholder = if (placeholder.isBlank()) null else ({ Text(placeholder) }),
        supportingText = supporting?.let { text -> ({ Text(text) }) },
        singleLine = singleLine,
        minLines = if (singleLine) 1 else 2,
        keyboardOptions = keyboardOptions,
        shape = RoundedCornerShape(17.dp),
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Accent,
            unfocusedBorderColor = Hairline,
            focusedContainerColor = Color.White,
            unfocusedContainerColor = Color.White
        )
    )
}

@Composable
private fun ModalActions(
    onCancel: () -> Unit,
    onConfirm: () -> Unit,
    confirmTitle: String,
    enabled: Boolean
) {
    Spacer(Modifier.height(16.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
        OutlinedButton(
            onClick = onCancel,
            modifier = Modifier.weight(1f).height(50.dp),
            shape = RoundedCornerShape(16.dp)
        ) { Text("Отмена") }
        Button(
            onClick = onConfirm,
            enabled = enabled,
            modifier = Modifier.weight(1f).height(50.dp),
            shape = RoundedCornerShape(16.dp)
        ) { Text(confirmTitle) }
    }
}

@Composable
private fun PrimaryButton(title: String, onClick: () -> Unit) {
    Button(
        onClick = onClick,
        modifier = Modifier.fillMaxWidth().height(54.dp),
        shape = RoundedCornerShape(18.dp)
    ) { Text(title, fontSize = 16.sp, fontWeight = FontWeight.SemiBold) }
}

@Composable
private fun BackLink(title: String, onClick: () -> Unit) {
    TextButton(onClick = onClick, contentPadding = PaddingValues(horizontal = 0.dp, vertical = 5.dp)) {
        Text("‹  $title", color = Accent, fontSize = 15.sp)
    }
}

@Composable
private fun EmptyHint(title: String, text: String) {
    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(horizontal = 28.dp)) {
        Text(title, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(5.dp))
        Text(text, color = Muted, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

@Composable
private fun CircleMark(text: String) {
    Box(
        Modifier.size(44.dp).background(Accent.copy(alpha = 0.10f), RoundedCornerShape(22.dp)),
        contentAlignment = Alignment.Center
    ) { Text(text, color = Accent, fontSize = 19.sp, fontWeight = FontWeight.Bold) }
}

@Composable
private fun MeterBadge(kind: String) {
    val preset = presets.firstOrNull { it.kind == kind } ?: presets.last()
    Box(
        Modifier.size(44.dp).background(Accent.copy(alpha = 0.10f), RoundedCornerShape(22.dp)),
        contentAlignment = Alignment.Center
    ) { Text(preset.mark, color = Accent, fontWeight = FontWeight.Bold, fontSize = 13.sp) }
}

@Composable
private fun ConfirmDialog(title: String, text: String, onDismiss: () -> Unit, onConfirm: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { Text(text) },
        confirmButton = { TextButton(onClick = onConfirm) { Text("Удалить", color = Danger) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } },
        shape = RoundedCornerShape(26.dp),
        containerColor = Color.White
    )
}

private fun sanitizeNumber(raw: String): String {
    val normalized = raw.replace('.', ',')
    val out = StringBuilder()
    var separatorUsed = false
    normalized.forEach { ch ->
        when {
            ch.isDigit() -> out.append(ch)
            ch == ',' && !separatorUsed -> {
                if (out.isEmpty()) out.append('0')
                out.append(',')
                separatorUsed = true
            }
        }
    }
    return out.toString().take(14)
}

private fun pluralMeter(count: Int): String {
    val n10 = count % 10
    val n100 = count % 100
    return when {
        n10 == 1 && n100 != 11 -> "счётчик"
        n10 in 2..4 && n100 !in 12..14 -> "счётчика"
        else -> "счётчиков"
    }
}

private fun formatValue(value: Double): String =
    if (value % 1.0 == 0.0) value.toLong().toString()
    else String.format(Locale.getDefault(), "%.3f", value).trimEnd('0').trimEnd(',', '.')

private fun formatDate(timestamp: Long): String =
    SimpleDateFormat("dd.MM.yyyy", Locale.getDefault()).format(Date(timestamp))

private fun formatDateTime(timestamp: Long): String =
    SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date(timestamp))
