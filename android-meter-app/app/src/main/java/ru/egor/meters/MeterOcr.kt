package ru.egor.meters

import android.content.Context
import android.net.Uri
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.util.Locale

object MeterOcr {
    private val recognizer by lazy {
        TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
    }

    fun recognize(
        context: Context,
        uriString: String,
        previousValue: Double?,
        onResult: (Result<Double?>) -> Unit
    ) {
        val uri = Uri.parse(uriString)
        val image = runCatching { InputImage.fromFilePath(context, uri) }
            .getOrElse {
                onResult(Result.failure(it))
                return
            }

        recognizer.process(image)
            .addOnSuccessListener { text ->
                val candidates = extractCandidates(text.text)
                val best = chooseBest(candidates, previousValue)
                onResult(Result.success(best))
            }
            .addOnFailureListener { error ->
                onResult(Result.failure(error))
            }
    }

    internal fun extractCandidates(raw: String): List<Double> {
        if (raw.isBlank()) return emptyList()

        val normalized = raw
            .replace('O', '0')
            .replace('o', '0')
            .replace('I', '1')
            .replace('l', '1')
            .replace(',', '.')

        val regex = Regex("(?<!\\d)\\d{1,9}(?:\\.\\d{1,4})?(?!\\d)")
        return regex.findAll(normalized)
            .mapNotNull { it.value.toDoubleOrNull() }
            .filter { it >= 0.0 }
            .distinct()
            .toList()
    }

    internal fun chooseBest(candidates: List<Double>, previousValue: Double?): Double? {
        if (candidates.isEmpty()) return null

        if (previousValue != null) {
            val notLower = candidates.filter { it >= previousValue }
            if (notLower.isNotEmpty()) {
                return notLower.minByOrNull { it - previousValue }
            }
        }

        return candidates.maxByOrNull { scoreCandidate(it) }
    }

    private fun scoreCandidate(value: Double): Double {
        val text = String.format(Locale.US, "%.4f", value).trimEnd('0').trimEnd('.')
        val digits = text.count { it.isDigit() }
        val decimalBonus = if ('.' in text) 1.5 else 0.0
        return digits + decimalBonus
    }
}
