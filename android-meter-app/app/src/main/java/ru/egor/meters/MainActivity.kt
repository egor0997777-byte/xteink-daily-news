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

data class Reading(
    val id: String = UUID.randomUUID().toString(),
    val value: Double,
    val timestamp: Long = System.currentTimeMillis(),
    val photoUri: String? = null
)

data class Meter(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val unit: String,
    val readings: List<Reading> = emptyList()
)

data class Address(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val meters: List<Meter> = emptyList()
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
                                            id = r.getString("id"),
                                            value = r.getDouble("value"),
                                            timestamp = r.getLong("timestamp"),
                                            photoUri = r.optString("photoUri").takeIf { it.isNotBlank() }
                                        )
                                    )
                                }
                            }
                            add(
                                Meter(
                                    id = m.getString("id"),
                                    name = m.getString("name"),
                                    unit = m.getString("unit"),
                                    readings = readings
                                )
                            )
                        }
                    }
                    add(Address(id = a.getString("id"), name = a.getString("name"), meters = meters))
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
                    )
                }
                metersJson.put(
                    JSONObject()
                        .put("id", meter.id)
                        .put("name", meter.name)
                        .put("unit", meter.unit)
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
                MeterApp(
                    repository = repository,
                    onTakePhoto = { callback -> launchCamera(callback) }
                )
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

    Surface(modifier = Modifier.fillMaxSize()) {
        when {
            selectedAddress == null -> HomeScreen(
                addresses = addresses,
                onOpen = { selectedAddressId = it },
                onAdd = { name -> persist(addresses + Address(name = name)) }
            )

            selectedMeter == null -> AddressScreen(
                address = selectedAddress,
                onBack = { selectedAddressId = null },
                onOpenMeter = { selectedMeterId = it },
                onAddMeter = { name, unit ->
                    persist(addresses.map { address ->
                        if (address.id == selectedAddress.id) {
                            address.copy(meters = address.meters + Meter(name = name, unit = unit))
                        } else address
                    })
                }
            )

            else -> MeterScreen(
                meter = selectedMeter,
                onBack = { selectedMeterId = null },
                onTakePhoto = onTakePhoto,
                onAddReading = { value, photoUri ->
                    persist(addresses.map { address ->
                        if (address.id != selectedAddress.id) return@map address
                        address.copy(meters = address.meters.map { meter ->
                            if (meter.id == selectedMeter.id) {
                                meter.copy(readings = meter.readings + Reading(value = value, photoUri = photoUri))
                            } else meter
                        })
                    })
                }
            )
        }
    }
}

@Composable
private fun HomeScreen(addresses: List<Address>, onOpen: (String) -> Unit, onAdd: (String) -> Unit) {
    var showAdd by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Text("Мои счётчики", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text("Выберите адрес", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(20.dp))

        if (addresses.isEmpty()) {
            Text("Пока нет ни одного адреса. Добавьте квартиру, дом или дачу.")
            Spacer(Modifier.height(16.dp))
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.weight(1f)) {
            items(addresses, key = { it.id }) { address ->
                Card(onClick = { onOpen(address.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(address.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        Text("Счётчиков: ${address.meters.size}", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) {
            Text("Добавить адрес")
        }
    }

    if (showAdd) {
        TextEntryDialog(
            title = "Новый адрес",
            label = "Название или адрес",
            onDismiss = { showAdd = false },
            onConfirm = { value -> onAdd(value); showAdd = false }
        )
    }
}

@Composable
private fun AddressScreen(
    address: Address,
    onBack: () -> Unit,
    onOpenMeter: (String) -> Unit,
    onAddMeter: (String, String) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Адреса") }
        Text(address.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(16.dp))

        if (address.meters.isEmpty()) {
            Text("Добавьте первый счётчик.")
            Spacer(Modifier.height(16.dp))
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.weight(1f)) {
            items(address.meters, key = { it.id }) { meter ->
                val last = meter.readings.maxByOrNull { it.timestamp }
                Card(onClick = { onOpenMeter(meter.id) }, modifier = Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp)) {
                        Text(meter.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        if (last == null) {
                            Text("Показаний ещё нет", color = MaterialTheme.colorScheme.onSurfaceVariant)
                        } else {
                            Text("Последнее: ${formatValue(last.value)} ${meter.unit}")
                            Text(formatDate(last.timestamp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("Добавить счётчик") }
    }

    if (showAdd) {
        AddMeterDialog(
            onDismiss = { showAdd = false },
            onConfirm = { name, unit -> onAddMeter(name, unit); showAdd = false }
        )
    }
}

@Composable
private fun MeterScreen(
    meter: Meter,
    onBack: () -> Unit,
    onTakePhoto: (((String?) -> Unit) -> Unit),
    onAddReading: (Double, String?) -> Unit
) {
    var showAdd by remember { mutableStateOf(false) }
    val sorted = meter.readings.sortedByDescending { it.timestamp }
    val latest = sorted.firstOrNull()
    val previous = sorted.getOrNull(1)

    Column(Modifier.fillMaxSize().padding(20.dp)) {
        TextButton(onClick = onBack) { Text("← Счётчики") }
        Text(meter.name, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))

        if (latest != null) {
            Text("${formatValue(latest.value)} ${meter.unit}", style = MaterialTheme.typography.headlineMedium)
            if (previous != null) {
                val delta = latest.value - previous.value
                Text("Расход с прошлого показания: ${formatValue(delta)} ${meter.unit}")
            }
            Text("Последнее показание: ${formatDate(latest.timestamp)}", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            Text("Показаний пока нет")
        }

        Spacer(Modifier.height(20.dp))
        Text("История", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.weight(1f)) {
            items(sorted, key = { it.id }) { reading ->
                Card(modifier = Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.fillMaxWidth().padding(14.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("${formatValue(reading.value)} ${meter.unit}", fontWeight = FontWeight.SemiBold)
                            Text(formatDate(reading.timestamp), color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (reading.photoUri != null) {
                            Text("📷", style = MaterialTheme.typography.titleLarge)
                        }
                    }
                }
            }
        }

        Button(onClick = { showAdd = true }, modifier = Modifier.fillMaxWidth()) { Text("Новое показание") }
    }

    if (showAdd) {
        AddReadingDialog(
            unit = meter.unit,
            previousValue = latest?.value,
            onTakePhoto = onTakePhoto,
            onDismiss = { showAdd = false },
            onConfirm = { value, photo -> onAddReading(value, photo); showAdd = false }
        )
    }
}

@Composable
private fun TextEntryDialog(
    title: String,
    label: String,
    onDismiss: () -> Unit,
    onConfirm: (String) -> Unit
) {
    var text by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = { OutlinedTextField(value = text, onValueChange = { text = it }, label = { Text(label) }, singleLine = true) },
        confirmButton = {
            TextButton(onClick = { if (text.isNotBlank()) onConfirm(text.trim()) }, enabled = text.isNotBlank()) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun AddMeterDialog(onDismiss: () -> Unit, onConfirm: (String, String) -> Unit) {
    var name by remember { mutableStateOf("") }
    var unit by remember { mutableStateOf("м³") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новый счётчик") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("Название") }, singleLine = true)
                OutlinedTextField(value = unit, onValueChange = { unit = it }, label = { Text("Единица измерения") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onConfirm(name.trim(), unit.trim()) },
                enabled = name.isNotBlank() && unit.isNotBlank()
            ) { Text("Добавить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

@Composable
private fun AddReadingDialog(
    unit: String,
    previousValue: Double?,
    onTakePhoto: (((String?) -> Unit) -> Unit),
    onDismiss: () -> Unit,
    onConfirm: (Double, String?) -> Unit
) {
    var valueText by remember { mutableStateOf("") }
    var photoUri by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    val parsedValue = valueText.replace(',', '.').toDoubleOrNull()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Новое показание") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (previousValue != null) {
                    Text("Предыдущее: ${formatValue(previousValue)} $unit")
                }
                OutlinedTextField(
                    value = valueText,
                    onValueChange = { valueText = it; error = null },
                    label = { Text("Показание, $unit") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    singleLine = true
                )
                OutlinedButton(onClick = {
                    onTakePhoto { result ->
                        photoUri = result
                        if (result == null) error = "Фото не сохранено"
                    }
                }) {
                    Text(if (photoUri == null) "Сфотографировать счётчик" else "Фото сохранено ✓")
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    val value = parsedValue ?: return@TextButton
                    if (previousValue != null && value < previousValue) {
                        error = "Новое показание меньше предыдущего. Проверьте цифры."
                    } else {
                        onConfirm(value, photoUri)
                    }
                },
                enabled = parsedValue != null
            ) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } }
    )
}

private fun formatDate(timestamp: Long): String =
    SimpleDateFormat("dd.MM.yyyy HH:mm", Locale.getDefault()).format(Date(timestamp))

private fun formatValue(value: Double): String =
    if (value % 1.0 == 0.0) value.toLong().toString() else String.format(Locale.getDefault(), "%.3f", value).trimEnd('0').trimEnd(',', '.')
